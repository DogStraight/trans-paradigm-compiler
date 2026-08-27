"""Lexer — tokenizer driven by _token.toml configuration.

Converts Verilog source text into a stream of Token objects.
Keyword/symbol/literal/comment/whitespace patterns are all defined
in TOML — no hardcoded lexer logic.

配置通过 ConfigRegistry 声明式加载。
Doc: docs/language_walkthrough.md（主扫描器）
"""

import os

from core.define import Token
from core.config_registry import declare_cfg
from core.token_protocol import (
    bracket_left,
    bracket_right,
    keyword_type,
    literal_type,
    macro_type,
    symbol_type,
)

from .lexer_utils import get_number_config
from .number_runner import build_number_runner
from .capture_runner import CaptureRunner, CaptureRule

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# preprocessor.macro_config（与 preprocessor/_expand.py 共享同一 key，宏配置
# 权威归属 preprocessor 段）：
#   { macro_recognition: { directive: { strategy, prefix }, call: { strategy, prefix } },
#     directives: { keyword: token_type, ... } }
_macro_cfg: dict = declare_cfg("preprocessor.macro_config", {}, __name__, "_macro_cfg")


def _build_unsized_prefixes(number_configs: list[dict] | None) -> set[str]:
    """无尺寸数字触发前缀集合（配置驱动，替代硬编码 'd/'h/'b/'o/'s）。

    从 [[number.based]] 形态推导：size = "none"（或 size.digits = "none"）
    且 base_prefix 为单字符（如 "'"）的形态，收集 prefix+base 组合
    （大小写变体）；signed 形态另加 prefix+"s"/"S"（如 verilog 的 'sd）。

    多字符前缀（0x 等）与无前缀形态（base_prefix="none"）不参与——
    它们的触发由 number 分支（isdigit）与 id 分支自然覆盖。
    """
    chars: set[str] = set()
    for cfg in number_configs or []:
        size = cfg.get("size")
        is_unsized = size == "none" or (
            isinstance(size, dict) and size.get("digits") == "none"
        )
        prefix = cfg.get("base_prefix")
        if (
            not is_unsized
            or not isinstance(prefix, str)
            or prefix in ("", "none")
            or len(prefix) != 1
        ):
            continue
        for base in cfg.get("bases", []) or []:
            base = str(base)
            chars.add(prefix + base.lower())
            chars.add(prefix + base.upper())
        if cfg.get("signed"):
            chars.add(prefix + "s")
            chars.add(prefix + "S")
    return chars


def _parse_char_class(segments: list) -> frozenset[str]:
    """解析字符类段列表 → 字符集合（[plain] first/continuation 配置）。

    段形态：单字符 "a" / 范围 "A-Z"（len 3 且中间 '-')。fail-fast：
    非法段直接报错（decisions/0003）。
    """
    chars: set[str] = set()
    for seg in segments:
        if not isinstance(seg, str) or not seg:
            raise ValueError(
                f"[lexer] [plain] 字符类段非法: {seg!r}（须为非空字符串，"
                "单字符或 A-Z 范围）"
            )
        if len(seg) == 3 and seg[1] == "-":
            for c in range(ord(seg[0]), ord(seg[2]) + 1):
                chars.add(chr(c))
        else:
            chars.update(seg)
    return frozenset(chars)


class Lexer:
    token_define: dict = {}

    def __init__(
        self,
        token_define_dict: dict | None = None,
        number_configs: list[dict] | None = None,
        rules_dir: str | None = None,
        ext_dirs: list[str] | None = None,
    ) -> None:
        if rules_dir:
            # 按语言包自包含解析（一次 resolve）：token 定义 / 宏配置 / 数字形态
            # 都跟随本实例的 rules_dir，不依赖最后一次 load_all 的全局状态——
            # 同一进程跨语言（测试/多语言服务）时不会串用上一语言的配置。
            from core.config_registry import ConfigRegistry
            from .lexer_utils import merge_token_define, extract_number_configs

            resolved = ConfigRegistry.resolve(
                rules_dir,
                ext_dirs=ext_dirs,
                plugins_dir=os.path.join(rules_dir, "plugins"),
            )
            if token_define_dict is None:
                token_define_dict = merge_token_define(resolved)
            raw_macro = resolved.get("preprocessor.macro_config", {}) or {}
            if number_configs is None:
                number_configs = extract_number_configs(
                    resolved.get("lexer.number", {})
                )
        else:
            # 无 rules_dir 的旧路径：直接读 token 文件 + 全局宏配置
            if token_define_dict is None:
                from .lexer_utils import get_token_define

                token_define_dict = get_token_define()
            raw_macro = _macro_cfg
            if number_configs is None:
                number_configs = get_number_config()
        self.token_define = token_define_dict

        # 宏识别策略与配置
        self._macro_dir_cfg: dict = raw_macro.get("macro_recognition", {}).get("directive", {})
        self._macro_call_cfg: dict = raw_macro.get("macro_recognition", {}).get("call", {})
        self.macro_config = {d: macro_type(d) for d in raw_macro.get("directives", {})}

        self.indent_enable = token_define_dict.get("indent", {}).get("enable", False)
        raw_level = token_define_dict.get("indent", {}).get("level", 4)
        # level = "auto"：缩进单位从文件启发式推导（首次结构缩进行锁定，
        # Python 同款）——YAML 文件缩进宽度不固定（2/4/6），固定网格无法
        # 解析 2 空格文件。固定 int 的语言包（verilog/c4 未启用 indent）不变。
        self.indent_auto = raw_level == "auto"
        self.indent_level = 4 if self.indent_auto else int(raw_level)
        # _indent_unit：auto 模式下的锁定单位（None = 未锁定，每次 tokenize 重置）
        self._indent_unit: int | None = None
        self.indent_deep = 0
        self.blank: list = list(token_define_dict.get("space", {}).values()) + list(
            token_define_dict.get("newline", {}).values()
        )
        self.newline: list = list(token_define_dict.get("newline", {}).values())
        self.alpha_tokens = []
        self._build_alpha_tokens()
        self.full_token_map: dict[str, str] = self._build_full_token_map()
        # capture mode 表（注释/字符串/heredoc/块标量等，配置驱动）：
        # 构建一次缓存，避免 tokenize 主循环每轮重建规则表。
        self._capture_rules: list[CaptureRule] = CaptureRunner.build_rules(
            self.token_define
        )
        self._capture_starts: list[str] = [r.start for r in self._capture_rules]
        self._capture_start_map: dict[str, CaptureRule] = {
            r.start: r for r in self._capture_rules
        }
        # 注释触发标记（auto 缩进锁定跳过注释行用）
        self._comment_starts: list[str] = [
            r.start for r in self._capture_rules if r.token_type == "comment"
        ]
        # 空白/换行字符集（plain 扫描终止判定用）
        self._space_set: frozenset[str] = frozenset(
            token_define_dict.get("space", {}).values()
        )
        self._newline_set: frozenset[str] = frozenset(self.newline)
        # 字符串定界符集合（[string] delimiters，引擎不再硬编码引号）：
        # 字符串分支在主循环后半段（number 之后），只在此命中。
        self._string_delims: set[str] = set(
            token_define_dict.get("string", {}).get("delimiters", [])
        )
        # 无尺寸数字触发前缀（'d/'h/'b/'o 等，从 lexer.number 形态推导）：
        # 替代硬编码 "dDbBhHoOsS"——无 size 形态 + 单字符 base_prefix 的
        # prefix+base 组合（大小写），signed 形态另加 prefix+s/S。
        self._unsized_prefixes: set[str] = _build_unsized_prefixes(number_configs)

        # plain scalar 配置（[plain] 段，YAML 类语言的裸标量扫描）：
        # first = 触发字符集；continuation = 续字符集（含空格，多词值）；
        # stop_space_after = 这些字符后随空白/行尾即终止（YAML 的 ':' 映射分隔）；
        # no_space_after_tokens = 前一个显著 token 在此集合时遇空格终止
        #   （锚点名/别名名是单词，不吞空格——'&anchor value' 拆两 token）。
        # 未声明 [plain] 的语言包（verilog/c4）→ 分支永不触发，零影响。
        plain_cfg = token_define_dict.get("plain", {}) or {}
        self._plain_first: frozenset[str] = _parse_char_class(
            plain_cfg.get("first", []) or []
        )
        self._plain_cont: frozenset[str] = _parse_char_class(
            plain_cfg.get("continuation", []) or []
        )
        self._plain_stop_space_after: frozenset[str] = frozenset(
            plain_cfg.get("stop_space_after", "") or ""
        )
        self._plain_no_space_tokens: frozenset[str] = frozenset(
            plain_cfg.get("no_space_after_tokens", []) or []
        )
        # flow 终止符：这些字符在括号内（bracket_depth > 0，流式集合语境）
        # 终止扫描（YAML flow 语境规则）——'{a: 1}' 的 '}' 必须终止 'a'，
        # 但块语境（depth 0）下吸收（'${{ matrix.os }}' 的 '{}' 是值的一部分）。
        self._plain_flow_stops: frozenset[str] = frozenset(
            plain_cfg.get("flow_terminators", []) or []
        )
        # fail-fast：触发字符必须是续字符子集（否则扫描空转死循环）
        if not self._plain_first.issubset(self._plain_cont):
            missing = "".join(sorted(self._plain_first - self._plain_cont))
            raise ValueError(
                "[lexer] [plain] first 字符不在 continuation 内: "
                + repr(missing)
                + "（first 须为 continuation 子集）"
            )
        # extend 符号优先表（'...' 文档结束符须先于 plain 的 '.' 触发）
        self._extend_values: list[str] = [
            v
            for v in self.token_define.get("symbol", {}).get("extend", {}).values()
            if isinstance(v, str) and len(v) > 1
        ]

        # 括号配对表 → 开闭集合 + 类型映射
        bracket_pairs: list = self.token_define.get("bracket", {}).get("pairs", [])
        self.open_brackets: set[str] = set()
        self.close_brackets: set[str] = set()
        self.bracket_type_map: dict[str, str] = {}
        for open_c, close_c, name in bracket_pairs:
            self.open_brackets.add(open_c)
            self.close_brackets.add(close_c)
            self.bracket_type_map[open_c] = bracket_left(name)
            self.bracket_type_map[close_c] = bracket_right(name)
        self.bracket_depth: int = 0

        self.previous_token_type: str = ""

        # new_line_start：行首标记，缩进处理用
        self.new_line_start = False
        # 行状态（capture 触发条件用）：
        # _line_indent = 当前行物理缩进列（行首空白宽，indent_leq 基准）；
        # _line_sig = 当前行最近一个显著 token 类型（after 条件用）。
        self._line_indent = 0
        self._line_sig: str | None = None

        # 数字解析器：配置驱动（语言包声明形态）→ 生成 FSM（唯一路径）。
        # 旧 NumberFSM 回退已移除（P2.1 配置化后所有语言包都声明数字形态，
        # 回退路径不可达且带旧 FSM 的过度匹配 bug：0x1F 被误认整体等）。
        # 形态缺失 = 配置错误，fail-fast（decisions/0003）。
        runner = build_number_runner(number_configs)
        if runner is None:
            raise RuntimeError(
                "[lexer] 数字形态未配置（lexer.number 缺失）——配置化数字是"
                "唯一路径，请检查语言包 base/_number.toml 是否声明 [[number.based]]"
            )
        self._number_runner = runner

    def _build_alpha_tokens(self) -> None:
        """构建字母形式 token 映射列表 (value, type)"""
        self.alpha_tokens.clear()

        # 1. symbol.base 和 symbol.extend
        for cat in ("base", "extend"):
            for sym_name, sym_value in (
                self.token_define.get("symbol", {}).get(cat, {}).items()
            ):
                if isinstance(sym_value, str) and sym_value.isalpha():
                    self.alpha_tokens.append(
                        (sym_value, symbol_type(cat, sym_name))
                    )

        # 2. bracket（来自 pairs 结构）
        for open_c, close_c, name in self.token_define.get("bracket", {}).get(
            "pairs", []
        ):
            if isinstance(open_c, str) and open_c.isalpha():
                self.alpha_tokens.append((open_c, bracket_left(name)))
            if isinstance(close_c, str) and close_c.isalpha():
                self.alpha_tokens.append((close_c, bracket_right(name)))

        # 3. literal 精确字面量（排除 string, number）
        for lit_name, lit_value in self.token_define.get("literal", {}).items():
            if lit_name in ("string", "number"):
                continue
            if isinstance(lit_value, str) and lit_value.isalpha():
                self.alpha_tokens.append((lit_value, literal_type(lit_name)))

    def tokenize(self, lex_text: str) -> list[Token]:
        lex_text_len: int = len(lex_text)
        lex_text = lex_text + "\n"  # add a newline at the end

        # 缩进深度每次 tokenize 重置：每个源文件是独立缩进上下文，
        # 跨调用残留会导致新文件开头误发 space.dedent（YAML 缩进语言包暴露）。
        self.indent_deep = 0
        self._indent_unit = None  # auto 模式：每个文件重新推导单位
        self._line_indent = 0
        self._line_sig = None

        # token pos relative
        text_idx: int = 0
        line_number: int = 1
        start_point: int = 0

        # tokens
        tokens = []

        while text_idx < lex_text_len:
            # token container
            current_token: Token = Token(line=line_number, column=start_point)

            # reset offset
            offset = 0

            # ── newline 分支 ──
            if lex_text[text_idx] in self.newline:
                start_point += 1

                current_token.set_type("newline")
                current_token.set_content(lex_text[text_idx])

                line_number += 1
                text_idx += 1
                start_point = 0
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                self.new_line_start = True
                # 行状态随换行重置
                self._line_indent = 0
                self._line_sig = None
                continue

            # ── space 分支 ──
            elif lex_text[text_idx] in self.token_define["space"].values():
                space_content: str = ""
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] in self.token_define["space"].values()
                ):
                    space_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # handle indentation only when this line just started
                if self.new_line_start:
                    # 记录本行物理缩进列（capture indent_leq 的终止基准）
                    self._line_indent = len(space_content)
                if self.new_line_start and self.indent_enable:
                    # empty line (only spaces followed by newline) -> ignore
                    if text_idx < lex_text_len and lex_text[text_idx] in self.newline:
                        self.new_line_start = True
                    else:
                        # 行首空格：先判 bracket 深度，再判网格对齐（auto 模式
                        # 首次结构缩进行锁定单位，Python 同款启发式）
                        width = len(space_content)
                        if self.bracket_depth > 0:
                            # 括号内：抑制一切结构缩进（仅用于对齐，非结构变化）
                            current_depth = self.indent_deep
                        elif (
                            self.indent_auto
                            and self._indent_unit is None
                            and not self._starts_comment(lex_text, text_idx)
                        ):
                            # 首次结构缩进：锁定单位（注释行不参与锁定——
                            # 注释缩进不代表文件结构约定）
                            self._indent_unit = width
                            current_depth = 1
                        elif not self._indent_aligned(width):
                            # 不对齐 → 续行折行，保持当前深度
                            current_depth = self.indent_deep
                        else:
                            # 对齐到缩进网格 → 结构深度变化
                            unit = (
                                self._indent_unit if self.indent_auto
                                else self.indent_level
                            )
                            # auto 模式已对齐 ⟹ _indent_unit 非 None（对齐判定前置）
                            assert unit is not None
                            current_depth = width // unit

                        if current_depth > self.indent_deep:
                            # 结构缩进
                            while self.indent_deep < current_depth:
                                indent_token = Token(
                                    line=line_number, column=start_point
                                )
                                indent_token.set_type("space.indent")
                                indent_token.set_content(space_content)
                                tokens.append(indent_token)
                                self.indent_deep += 1
                        elif current_depth < self.indent_deep:
                            # 结构反缩进
                            while self.indent_deep > current_depth:
                                dedent_token = Token(
                                    line=line_number, column=start_point
                                )
                                dedent_token.set_type("space.dedent")
                                dedent_token.set_content("")
                                tokens.append(dedent_token)
                                self.indent_deep -= 1
                        else:  # current_depth == self.indent_deep
                            # 同深度：不对齐且括号外才是折行
                            if (
                                self.bracket_depth == 0
                                and not self._indent_aligned(width)
                            ):
                                fold_token = Token(line=line_number, column=start_point)
                                fold_token.set_type("space.fold")
                                fold_token.set_content("")
                                tokens.append(fold_token)

                        self.new_line_start = False
                # else: ignore

                # update start_point
                start_point += len(space_content)
                continue

            # capture — 原始文本捕获（CommentRunner 泛化：注释/heredoc/
            # 围栏/块标量等"进入后原样吞字符"构造统一走 CaptureRunner，
            # 完全配置驱动；after/next_chars 触发条件由 _match_capture 判定）
            elif self._match_capture(lex_text, text_idx) is not None:
                result = CaptureRunner.run(
                    lex_text, text_idx, self.token_define,
                    base_col=self._line_indent,
                )
                if result is not None:
                    capture_content, new_idx, token_type = result
                    self._emit_pending_dedent(tokens)
                    current_token.set_type(token_type)
                    current_token.set_content(capture_content)
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    offset = new_idx - text_idx
                    text_idx = new_idx
                    # 多行捕获跨行：行号/列按消费的原文跨度记账（此前只平移
                    # 列、行号不增，捕获后的 token 行号系统性偏少）。
                    newlines = lex_text.count("\n", text_idx - offset, new_idx)
                    if newlines:
                        line_number += newlines
                        start_point = new_idx - (
                            lex_text.rfind("\n", 0, new_idx) + 1
                        )
                    else:
                        start_point += offset
                    # 捕获终止于行边界（最后一个消费字符是换行）→ 下一个
                    # token 在行首，置行首标记使缩进机制正确工作。
                    if new_idx > 0 and lex_text[new_idx - 1] in self.newline:
                        self.new_line_start = True
                    # captures at beginning of line should not affect indentation
                    elif self.new_line_start:
                        self.new_line_start = False
                    continue

            # plain scalar — 裸标量（[plain] 配置驱动，YAML plain scalar 近似）：
            # 单 token 扫描到行尾（含词内空格的多词值），终止规则
            # （stop_space_after 映射分隔 / no_space_after_tokens 单词边界）
            # 与字符集全部来自配置。extend 符号优先（'...' 文档结束符先于
            # plain 的 '.' 触发）。未声明 [plain] 的语言包分支不触发。
            elif (
                self._plain_first
                and lex_text[text_idx] in self._plain_first
                and not self._extend_symbol_at(lex_text, text_idx)
            ):
                self._emit_pending_dedent(tokens)

                scalar_content, new_idx = self._scan_plain_scalar(
                    lex_text, text_idx
                )
                offset = new_idx - text_idx
                text_idx = new_idx
                current_token.set_content(scalar_content)
                # 关键字精化（true/false/null 等经 flat map 升级为 keyword）
                full = self.full_token_map.get(scalar_content)
                current_token.set_type(full if full is not None else "literal.plain")
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── 无尺寸字面量分支（'b1/'d0/'hFF/'o7，配置驱动触发）──
            # 触发集合从 lexer.number 形态推导（无 size + 单字符 base_prefix），
            # 不再硬编码 'd/'h/'b/'o/'s 字符表——yaml/c4 无 ' 数字形态时
            # ' 自然落到后续字符串/symbol 分支。
            elif (
                lex_text[text_idx:text_idx + 2] in self._unsized_prefixes
            ):
                self._emit_pending_dedent(tokens)

                number_content, new_idx = self._number_runner.run(lex_text, text_idx)
                offset = new_idx - text_idx

                # runner 空结果（如 `'d` 无 value）：防死循环，退化为符号
                if not number_content or offset <= 0:
                    text_idx += 1
                    start_point += 1
                    current_token.set_content(lex_text[text_idx - 1])
                    current_token.set_type("symbol.base")
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    continue

                current_token.set_type("literal.number")
                current_token.set_content(number_content)

                text_idx = new_idx
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── symbol 分支 ──
            elif lex_text[text_idx] in self.token_define["symbol"]["base"].values():
                # handle possible dedent before actual token
                self._emit_pending_dedent(tokens)

                # 最长匹配：从 base 字符起贪心扩展，extend 表里有什么就支持
                # 多长（如 >>>/<<< 三字符，配置驱动，不硬编码符号长度）。
                extend_values = self.token_define["symbol"]["extend"].values()
                current_token.set_content(lex_text[text_idx])
                current_token.set_type("symbol.base")
                text_idx += 1
                offset += 1
                candidate = current_token.content
                while text_idx < lex_text_len:
                    probe = candidate + lex_text[text_idx]
                    if probe in extend_values:
                        candidate = probe
                        text_idx += 1
                        offset += 1
                    else:
                        break
                if len(candidate) > 1:
                    current_token.set_content(candidate)
                    current_token.set_type("symbol.extend")

                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── bracket 分支 ──
            elif (
                lex_text[text_idx] in self.open_brackets
                or lex_text[text_idx] in self.close_brackets
            ):
                self._emit_pending_dedent(tokens)

                # 跟踪括号深度
                if lex_text[text_idx] in self.open_brackets:
                    self.bracket_depth += 1
                else:
                    self.bracket_depth -= 1

                current_token.set_type("bracket")
                current_token.set_content(lex_text[text_idx])

                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # (comment/capture handled by CaptureRunner in earlier branch)

            # ── 转义标识符分支（IEEE 1364-2005 A.9.3 escaped_identifier）──
            # `\` + 非空白字符序列，到空白或语法分隔符止（`,;()[]{}`），如
            # `\a.b`、`\my$mod`。token 类型置 id（保留 `\` 前缀），refine_type
            # 的 keyword 精化不适用——转义标识符显式不受关键字限制
            # （`\always` 是合法名）。
            # 与 sv-parser 差异（各有取舍）：sv-parser 严格"到空白止"
            # （`wire \a.b;` 须写 `\a.b ;`），tpc 宽进——分隔符提前终止使
            # 业界常见写法 `wire \a.b;` 直接可解析且幂等；名字内含分隔符
            # 的极端形态（`\a;b`）不支持，记录为已知限制。
            elif lex_text[text_idx] == "\\":
                self._emit_pending_dedent(tokens)

                id_content = "\\"
                text_idx += 1
                offset += 1
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] not in " \t\r\n,;()[]{}"
                ):
                    id_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                current_token.set_type("id")
                current_token.set_content(id_content)

                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── id 分支 ──
            elif lex_text[text_idx].isalpha() or lex_text[text_idx] == "_":
                self._emit_pending_dedent(tokens)

                id_content: str = lex_text[text_idx]
                text_idx += 1
                offset += 1  # 首字符也要计入列偏移（否则后续 token 列号累积偏左）
                while text_idx < lex_text_len and (
                    lex_text[text_idx].isalpha()
                    or lex_text[text_idx] == "_"
                    or lex_text[text_idx].isdigit()
                ):
                    id_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                current_token.set_type("id")
                current_token.set_content(id_content)

                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── 宏 token 识别（prefix 策略）──
            #
            # 按 directive → call 顺序检查，相同前缀时 directive 优先。
            # 命中 directives 表 → macro.<key>；未命中且 call 策略相同 → macro.call。
            #
            dir_prefix = (
                self._macro_dir_cfg.get("prefix", "")
                if self._macro_dir_cfg.get("strategy") == "prefix"
                else ""
            )
            call_prefix = (
                self._macro_call_cfg.get("prefix", "")
                if self._macro_call_cfg.get("strategy") == "prefix"
                else ""
            )
            ch = lex_text[text_idx]
            matched_prefix = ""
            check_dir = False
            if dir_prefix and ch == dir_prefix:
                matched_prefix = dir_prefix
                check_dir = True
            elif call_prefix and ch == call_prefix:
                matched_prefix = call_prefix

            if matched_prefix:
                self._emit_pending_dedent(tokens)
                macro_content = ch
                text_idx += 1
                while text_idx < lex_text_len and (
                    lex_text[text_idx].isalpha()
                    or lex_text[text_idx] == "_"
                    or lex_text[text_idx].isdigit()
                ):
                    macro_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                macro_name = macro_content[1:]  # 去掉前缀
                macro_type = (
                    self.macro_config.get(macro_name, "macro.call")
                    if check_dir
                    else "macro.call"
                )
                current_token.set_type(macro_type)
                current_token.set_content(macro_content)

                start_point += len(macro_content)
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── number 分支 ──
            elif lex_text[text_idx].isdigit():
                self._emit_pending_dedent(tokens)

                number_content, new_idx = self._number_runner.run(lex_text, text_idx)
                offset = new_idx - text_idx

                # runner 返回空（形态不匹配）：不消费字符，交给后续分支
                # （防死循环：text_idx 必须前进）
                if not number_content or offset <= 0:
                    text_idx += 1
                    start_point += 1
                    current_token.set_content(lex_text[text_idx - 1])
                    current_token.set_type("id")
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    continue

                current_token.set_type("literal.number")
                current_token.set_content(number_content)

                text_idx = new_idx
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── 字符串分支 ──
            # 定界符来自 [string] delimiters 配置（delim capture mode），
            # 扫描逻辑走 CaptureRunner——引擎不再硬编码 "'/ 引号。
            # 未闭合遇换行不消费（字符串不跨行，修正旧实现的吞换行行为）。
            elif lex_text[text_idx] in self._string_delims:
                self._emit_pending_dedent(tokens)

                result = CaptureRunner.run(lex_text, text_idx, self.token_define)
                if result is None:  # 防御：delims 集合与 mode 表应一致
                    text_idx += 1
                    start_point += 1
                    current_token.set_content(lex_text[text_idx - 1])
                    current_token.set_type("unrecognized")
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    continue
                string_content, new_idx, _ = result
                offset = new_idx - text_idx
                text_idx = new_idx

                current_token.set_type("literal.string")
                current_token.set_content(string_content)

                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── 未识别分支 ──
            else:
                self._emit_pending_dedent(tokens)

                current_token.set_type("unrecognized")
                current_token.set_content(lex_text[text_idx])

                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
        return tokens

    def _emit_pending_dedent(self, tokens: list[Token]) -> None:
        """当新行没有前导空格时，输出所有待处理的 dedent 令牌"""
        if self.new_line_start:
            while self.indent_deep > 0:
                dedent_token = Token(line=0, column=0)
                dedent_token.set_type("space.dedent")
                dedent_token.set_content("")
                tokens.append(dedent_token)
                self.indent_deep -= 1
            self.new_line_start = False

    def _build_full_token_map(self) -> dict[str, str]:
        """构建 {原始字符串: 完整类型名} 的扁平映射表"""
        m: dict[str, str] = {}
        # bracket（来自 pairs）
        for open_c, close_c, name in self.token_define.get("bracket", {}).get(
            "pairs", []
        ):
            m[open_c] = bracket_left(name)
            m[close_c] = bracket_right(name)
        # symbol.base
        for name, val in self.token_define.get("symbol", {}).get("base", {}).items():
            if isinstance(val, str):
                m[val] = symbol_type("base", name)
        # symbol.extend
        for name, val in self.token_define.get("symbol", {}).get("extend", {}).items():
            if isinstance(val, str):
                m[val] = symbol_type("extend", name)
        # literal 精确匹配（排除 string/number 等由 lexer 正则处理的）
        for name, val in self.token_define.get("literal", {}).items():
            if name in ("string", "number"):
                continue
            if isinstance(val, str):
                m[val] = literal_type(name)
        # keyword（从 token_define["id"]["keyword"] 加载）
        for _, orig in self.token_define.get("id", {}).get("keyword", {}).items():
            if isinstance(orig, str):
                m[orig] = keyword_type(orig)
        return m

    # 仅供 tokenize 内部调用
    def _indent_aligned(self, width: int) -> bool:
        """行首空白宽是否对齐当前缩进网格（auto 未锁定 = 不对齐）。"""
        if self.indent_auto:
            return self._indent_unit is not None and width % self._indent_unit == 0
        return width % self.indent_level == 0

    # 仅供 tokenize 内部调用
    def _starts_comment(self, text: str, idx: int) -> bool:
        """idx 处（行首空白后）是否以注释标记开头（auto 锁定跳过注释行）。"""
        return any(text.startswith(s, idx) for s in self._comment_starts)

    # 仅供 tokenize 内部调用
    def _extend_symbol_at(self, text: str, idx: int) -> bool:
        """idx 处是否命中多字符 extend 符号（'...' 优先于 plain 的 '.' 触发）。"""
        return any(
            text.startswith(v, idx) for v in self._extend_values
        )

    # 仅供 tokenize 内部调用
    def _scan_plain_scalar(self, text: str, idx: int) -> tuple[str, int]:
        """从 idx 扫描 plain scalar（[plain] 配置驱动，YAML plain scalar 近似）。

        终止规则（配置声明，引擎无 YAML 具体知识）：
        - 换行 / EOF：终止（不消费）
        - stop_space_after 字符（如 ':'）后随空白/行尾：终止（映射分隔）
        - 空格后随 stop_before_comment… 注：注释终止靠"空格 + 注释分支"自然
          实现——空格不在续字符集时即终止；此处空格在续字符集（多词值），
          由 stop_before_comment 字符（'#'）判定：空格后随 '#' → 终止
          （'#' 留给注释分支，`abc#def` 的 '#' 前无空格 → 词内续字符）
        - no_space_after_tokens：前一个显著 token（锚点/别名名）后遇空格终止
        返回 (content, new_idx)；content 尾部空白已剥。
        """
        content = ""
        stop_comment_chars = self._comment_starts
        while idx < len(text):
            ch = text[idx]
            if ch in self._newline_set:
                break
            nxt = text[idx + 1] if idx + 1 < len(text) else ""
            # 空格后随注释标记 → 终止（注释留给注释分支）
            if ch in self._space_set and any(
                text.startswith(cs, idx + 1) for cs in stop_comment_chars
            ):
                break
            # 前一个显著 token 是锚点/别名 → 空格是单词边界（不吞）
            if (
                ch in self._space_set
                and self._line_sig in self._plain_no_space_tokens
            ):
                break
            # stop_space_after 字符后随空白/行尾 → 终止
            if ch in self._plain_stop_space_after and (
                not nxt or nxt in self._space_set or nxt in self._newline_set
            ):
                break
            # flow 语境终止符：括号内（流式集合）遇 { } 终止
            if ch in self._plain_flow_stops and self.bracket_depth > 0:
                break
            if ch not in self._plain_cont:
                break
            content += ch
            idx += 1
        # 剥尾部空白（多词值行尾的空格不保留）
        return content.rstrip(" "), idx

    # 仅供 tokenize 内部调用
    def _match_capture(self, text: str, pos: int) -> CaptureRule | None:
        """capture mode 触发匹配：start 前缀 + after + next_chars 条件。

        条件不满足返回 None——调用方（elif 链）不消费，落到后续分支
        （如 YAML `a | b` 的 `|` 不在值位置，不触发块标量）。
        """
        for s in self._capture_starts:
            if text.startswith(s, pos):
                rule = self._capture_start_map[s]
                # after：前一个显著 token 须在集合（值位置判定）
                if rule.after and self._line_sig not in rule.after:
                    return None
                # next_chars：后随字符须在集合（排除中缀场景，如 a | b）
                nxt = pos + rule.start_len
                if rule.next_set and (
                    nxt >= len(text) or text[nxt] not in rule.next_set
                ):
                    return None
                return rule
        return None

    # 仅供 tokenize 内部调用
    def refine_type(self, _token: Token) -> Token:
        # 粗类型精化：keyword/bracket/symbol 等字母形式查扁平表
        if _token.type == "unrecognized":
            raise ValueError(f"Unexpected token: {_token.content} ")
        if _token.type == "id":
            # 扁平映射表查找：覆盖 keyword / bracket / symbol 等字母形式
            full_type = self.full_token_map.get(_token.content)
            if full_type is not None:
                _token.type = full_type
            else:
                _token.type = "id"
        elif _token.type in ("bracket", "symbol.base", "symbol.extend"):
            full_type = self.full_token_map.get(_token.content)
            if full_type is not None:
                _token.type = full_type
        # else: 保持原有类型（newline / space / literal.string / literal.number / comment 等）
        self.previous_token_type = _token.type
        # 行内显著 token 记录（capture after 条件用；trivia 不计）
        if _token.type not in ("newline", "comment"):
            self._line_sig = _token.type
        return _token
