"""Lexer — tokenizer driven by _token.toml configuration.

Converts Verilog source text into a stream of Token objects.
Keyword/symbol/literal/comment/whitespace patterns are all defined
in TOML — no hardcoded lexer logic.

配置通过 ConfigRegistry 声明式加载。
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
from .comment_runner import CommentRunner

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# preprocessor.macro_config（与 preprocessor/_expand.py 共享同一 key，宏配置
# 权威归属 preprocessor 段）：
#   { macro_recognition: { directive: { strategy, prefix }, call: { strategy, prefix } },
#     directives: { keyword: token_type, ... } }
_macro_cfg: dict = declare_cfg("preprocessor.macro_config", {}, __name__, "_macro_cfg")


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
        self.indent_level = token_define_dict.get("indent", {}).get("level", 4)
        self.indent_deep = 0
        self.blank: list = list(token_define_dict.get("space", {}).values()) + list(
            token_define_dict.get("newline", {}).values()
        )
        self.newline: list = list(token_define_dict.get("newline", {}).values())
        self.alpha_tokens = []
        self._build_alpha_tokens()
        self.full_token_map: dict[str, str] = self._build_full_token_map()

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

            # get next char
            next_char: str = ""
            if text_idx + 1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

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
                if self.new_line_start and self.indent_enable:
                    # empty line (only spaces followed by newline) -> ignore
                    if text_idx < lex_text_len and lex_text[text_idx] in self.newline:
                        self.new_line_start = True
                    else:
                        # 行首空格：先判 bracket 深度，再用能否整除判断折行
                        if self.bracket_depth > 0:
                            # 括号内：抑制一切结构缩进（仅用于对齐，非结构变化）
                            current_depth = self.indent_deep
                        elif len(space_content) % self.indent_level != 0:
                            # 不对齐 → 续行折行，保持当前深度
                            current_depth = self.indent_deep
                        else:
                            # 对齐到缩进网格 → 结构深度变化
                            current_depth = len(space_content) // self.indent_level

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
                                and len(space_content) % self.indent_level != 0
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

            # comment — 使用 CommentRunner 解析（完全配置驱动）
            elif any(
                lex_text[text_idx : text_idx + len(s)] in (s,)
                for s in CommentRunner.get_start_patterns(self.token_define)
            ):
                result = CommentRunner.run(lex_text, text_idx, self.token_define)
                if result is not None:
                    comment_content, new_idx, _ = result
                    self._emit_pending_dedent(tokens)
                    current_token.set_type("comment")
                    current_token.set_content(comment_content)
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    offset = new_idx - text_idx
                    text_idx = new_idx
                    # 多行块注释跨行：行号同步前进（此前只平移列、行号不增，
                    # 注释后的所有 token 行号系统性偏少）；列重算到注释最后一
                    # 行内（该行注释内容宽度），单行注释仍按列平移 offset。
                    newlines = comment_content.count("\n")
                    if newlines:
                        line_number += newlines
                        start_point = (
                            len(comment_content) - comment_content.rfind("\n") - 1
                        )
                    else:
                        start_point += offset
                    # comments at beginning of line should not affect indentation
                    if self.new_line_start:
                        self.new_line_start = False
                    continue

            # ── 无尺寸字面量分支（'b1/'d0/'hFF/'o7/'s）──
            elif lex_text[text_idx] == "'" and next_char in "dDbBhHoOsS":
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

            # (comment handled by CommentRunner in earlier branch)

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
            elif lex_text[text_idx] == '"' or lex_text[text_idx] == "'":
                self._emit_pending_dedent(tokens)

                end_char: str = lex_text[text_idx]
                string_content: str = ""
                string_content += lex_text[text_idx]
                text_idx += 1
                offset += 1  # 起始引号计入列偏移
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] != end_char
                    and lex_text[text_idx] != "\n"
                ):
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1
                if text_idx < lex_text_len:
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1  # 结束引号计入列偏移

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
        return _token
