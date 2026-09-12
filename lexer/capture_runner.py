"""capture_runner.py — 配置驱动的原始文本捕获扫描器（CaptureRunner）

抽象原语：从当前字符开始"原样捕获"一段文本（不做 token 化），按终止
条件结束，产出一个 token。注释（行/块）与引号字符串都是 capture mode
表中的一个实例；heredoc/围栏代码块等同类构造均可作为配置项加入——
引擎不再硬编码任何"捕获类"语言知识（原 CommentRunner 只服务注释、原
字符串分支硬编码 "'/ 定界符，现统一由本类执行）。

配置面（token_define 三段，build_rules 归一化合并）：
1. [comment] pairs（legacy 兼容，三个语言包现有声明零改动）：
   pairs = [["#", "\\n", "line"], ["/*", "*/", "block"]]
   → kind "line" 终止于换行字符集；kind "block" 归一化为 "marker"（到
     end 标记）；token_type 固定为 "comment"。
2. [string] delimiters（字符串定界符，引擎不再硬编码 "'/ 引号）：
   delimiters = ['"', "'"]
   → 每个定界符展开为 kind "delim" 规则（end = 定界符自身），
     token_type 固定为 "literal.string"。
3. [[capture]] 段（新，语言包按需声明）：
   [[capture]]
   start = "<<EOF"
   end = "EOF"
   kind = "line_match"
   token_type = "literal.heredoc"

kind 语义（终止条件）：
- "line"      : 到换行字符（[newline] 段配置，不硬编码 \\n）或 EOF；
                换行字符不消费（留给主循环）
- "marker"    : 到 end 标记（消费）或 EOF（未闭合自然终止）
- "delim"     : 到 end 定界符（消费，含定界符本身）或换行（不消费——
                字符串不跨行）或 EOF（未闭合自然终止）
- "line_match": 到"一行恰好等于 end"处（heredoc/围栏：`<<EOF ... EOF`
                终止于独立成行的 EOF）；end 后的换行不消费

多行捕获的行号记账由调用方（main_lexer）处理（与既有 comment 分支一致）。

Doc: docs/language_walkthrough.md（注释/字符串 token 扫描）
"""

from __future__ import annotations


class CaptureRule:
    """一种原始捕获模式的匹配规则。"""

    def __init__(
        self,
        start: str,
        end: str,
        kind: str,
        token_type: str,
        after: tuple[str, ...] = (),
        next_chars: str = "",
    ):
        self.start = start  # 触发标记，如 "#" / "<<EOF" / "|"
        self.end = end  # 终止标记（marker/line_match/delim 用）
        self.kind = kind  # "line" | "marker" | "delim" | "line_match" | "indent_leq"
        self.token_type = token_type  # 产出 token 类型，如 "comment"
        self.start_len = len(start)
        self.end_len = len(end)
        # 触发上下文条件（由调用方 lexer 判定，本类不持有行状态）：
        # after = 前一个显著 token 类型须在此集合（YAML 块标量：须在
        #   ":" 或 "-" 值位置）；空 = 不限制。
        # next_chars = 后随字符须在此集合（YAML 块标量：须后随空白/换行/
        #   指示符，排除 a | b 的中缀场景）；空 = 不限制。
        self.after = after
        self.next_set = frozenset(next_chars)


_VALID_KINDS = ("line", "marker", "delim", "line_match", "indent_leq")


class CaptureRunner:
    """从 token_define 构建 capture mode 表并扫描文本。

    归一化入口 build_rules：合并 [comment] pairs（legacy）与 [capture]
    （新段）。排序保证长 start 优先匹配（如 "<<EOF" 在 "<<" 前，
    "/*" 在 "/" 前——与 legacy CommentRunner 的排序语义一致）。
    """

    @staticmethod
    def build_rules(token_define: dict) -> list[CaptureRule]:
        """从配置构建 capture 规则列表（legacy comment + 新 capture 段）。

        fail-fast（decisions/0003）：非法 kind 直接报错，不静默降级
        （legacy CommentRunner 对未知 kind 静默 return None——本类修正）。
        """
        rules: list[CaptureRule] = []

        # 1. legacy [comment] pairs → token_type = "comment"
        pairs = token_define.get("comment", {}).get("pairs", [])
        for item in pairs:
            if len(item) >= 3:
                start, end, legacy_kind = item[0], item[1], item[2]
            elif len(item) == 2:
                start, end = item[0], item[1]
                legacy_kind = "line"
            else:
                continue
            kind = "marker" if legacy_kind == "block" else legacy_kind
            if kind not in _VALID_KINDS:
                raise ValueError(
                    "[lexer] [comment] pairs 含未知 kind: "
                    f"{legacy_kind!r}（合法: line / block）"
                )
            rules.append(CaptureRule(start, end, kind, "comment"))

        # 2. [string] delimiters → kind = "delim"，token_type = "literal.string"
        #    （引擎不再硬编码引号定界符；verilog 只声明 "，yaml/c4 声明 " 与 '）
        for delim in token_define.get("string", {}).get("delimiters", []) or []:
            if not isinstance(delim, str) or not delim:
                raise ValueError(
                    "[lexer] [string] delimiters 含非法条目: "
                    f"{delim!r}（须为非空字符串）"
                )
            rules.append(
                CaptureRule(delim, delim, "delim", "literal.string")
            )

        # 3. 新 [capture] 段（TOML 数组表 [[capture]] → dict 列表）
        modes = token_define.get("capture")
        if isinstance(modes, list):
            for mode in modes:
                if not isinstance(mode, dict):
                    continue
                kind = mode.get("kind")
                token_type = mode.get("token_type")
                if kind not in _VALID_KINDS or not token_type:
                    raise ValueError(
                        "[lexer] [capture] 段配置不完整："
                        f"mode={mode!r}（需要 kind ∈ {_VALID_KINDS} + token_type）"
                    )
                # indent_leq 的终止条件是列比较（base_col 运行时传入），无需 end
                if kind not in ("line", "indent_leq") and not mode.get("end"):
                    raise ValueError(
                        "[lexer] [capture] 段配置不完整："
                        f"kind={kind!r} 需要非空 end 终止标记，mode={mode!r}"
                    )
                after = mode.get("after", [])
                if not isinstance(after, list):
                    raise ValueError(
                        "[lexer] [capture] 段配置不完整："
                        f"after 须为 token 类型列表，mode={mode!r}"
                    )
                next_chars = mode.get("next_chars", "")
                rules.append(
                    CaptureRule(
                        start=str(mode["start"]),
                        end=str(mode.get("end", "")),
                        kind=kind,
                        token_type=str(token_type),
                        after=tuple(str(t) for t in after),
                        next_chars=str(next_chars),
                    )
                )

        # 按起始标记长度降序：长标记优先（/* 在 / 前、<<EOF 在 << 前）
        rules.sort(key=lambda r: -r.start_len)
        return rules

    @staticmethod
    def get_start_patterns(token_define: dict) -> list[str]:
        """获取所有 capture mode 的触发标记，供 lexer 预判断。"""
        return [r.start for r in CaptureRunner.build_rules(token_define)]

    @staticmethod
    def run(
        text: str, start: int, token_define: dict, base_col: int = 0
    ) -> tuple[str, int, str] | None:
        """从 start 位置尝试匹配任意 capture mode。

        Args:
            base_col: 触发行的物理缩进列（indent_leq 的终止基准）。

        Returns:
            (content, end_pos, token_type) — 捕获内容、结束位置（消费到的
            下标，不含换行终止符）、产出 token 类型
            None — 当前位置不匹配任何 mode
        """
        rules = CaptureRunner.build_rules(token_define)
        newline_set = set(token_define.get("newline", {}).values())
        space_set = set(token_define.get("space", {}).values())
        for rule in rules:
            # 检查是否以起始标记开头
            if text[start : start + rule.start_len] != rule.start:
                continue

            pos = start + rule.start_len
            content = text[start:pos]

            if rule.kind == "line":
                # 到换行字符或 EOF，不消费换行
                while pos < len(text) and text[pos] not in newline_set:
                    content += text[pos]
                    pos += 1
                return (content, pos, rule.token_type)

            elif rule.kind == "marker":
                # 到 end 标记（消费）或 EOF（未闭合自然终止）
                while pos < len(text):
                    if text[pos : pos + rule.end_len] == rule.end:
                        content += text[pos : pos + rule.end_len]
                        pos += rule.end_len
                        return (content, pos, rule.token_type)
                    content += text[pos]
                    pos += 1
                # 未闭合（EOF 自然终止）：tokenize 会在输入末尾追加换行
                # （main_lexer 确保尾 token 处理），该追加换行会被 marker
                # 吞进 content——`/*` → `/*\n`，下一轮 `/*\n` + 追加 `\n`
                # → `/*\n\n` 无限增长（format 幂等破坏）。剥掉尾部换行：
                # 未闭合注释的 token 内容不含追加的终止换行，渲染时按
                # 注释原样输出。
                if content.endswith(tuple(newline_set)):
                    content = content[:-1]
                return (content, pos, rule.token_type)

            elif rule.kind == "delim":
                # 到 end 定界符（消费，含定界符本身）或换行（不消费，
                # 字符串不跨行）或 EOF（未闭合自然终止）。
                # end 按**长度**比较（与 marker/line_match 同构）：此前用
                # `ch == rule.end` 单字符比较，多字符定界符（`"""`）永不
                # 匹配 → 静默吞到行尾/EOF（把后续 token 一起吃掉）。
                end_len = rule.end_len
                while pos < len(text):
                    if text[pos : pos + end_len] == rule.end:
                        content += rule.end
                        pos += end_len
                        return (content, pos, rule.token_type)
                    if text[pos] in newline_set:
                        return (content, pos, rule.token_type)
                    content += text[pos]
                    pos += 1
                return (content, pos, rule.token_type)

            elif rule.kind == "line_match":
                # 到"一行恰好等于 end"处；end 后的换行不消费
                while pos < len(text):
                    if text[pos : pos + rule.end_len] == rule.end:
                        # 前置必须是行首（pos 处是行起点）或换行后紧邻
                        at_line_start = (
                            pos == start + rule.start_len
                            or text[pos - 1] in newline_set
                        )
                        after = pos + rule.end_len
                        if at_line_start and (
                            after >= len(text) or text[after] in newline_set
                        ):
                            return (content, pos, rule.token_type)
                    content += text[pos]
                    pos += 1
                return (content, pos, rule.token_type)

            elif rule.kind == "indent_leq":
                # YAML 块标量：指示符行（start → 行尾含换行）原样入 content，
                # 然后逐行捕获"列 > base_col"的内容行（含空行——空行是
                # 内容），遇"非空且列 ≤ base_col"的行终止（该行不消费）。
                # 终止基准 = 触发行的物理缩进列（base_col，由 lexer 传入
                # 行首空白宽度）。缩进指示/切块指示（|-/|+/|2）原样保留
                # （与指示符行一体捕获，不做语义展开）。
                while pos < len(text) and text[pos] not in newline_set:
                    content += text[pos]
                    pos += 1
                if pos < len(text):  # 指示符行换行
                    content += text[pos]
                    pos += 1
                while pos < len(text):
                    line_start = pos
                    # 行首空白 → 物理列（tab 计 1 列，宽容）
                    p = pos
                    while p < len(text) and text[p] in space_set:
                        p += 1
                    col = p - line_start
                    # 行尾（不含换行）
                    eol = p
                    while eol < len(text) and text[eol] not in newline_set:
                        eol += 1
                    if eol > p and col <= base_col:
                        break  # 终止行（非空、列 ≤ 基准）：不消费
                    # 内容行（含空行）：整行含换行入 content
                    if eol < len(text):
                        eol += 1  # 含换行
                    content += text[line_start:eol]
                    pos = eol
                # 剥一个尾部换行：渲染时节点间 join "\n" 恰好补回，避免
                # 输出空行（字面块 clip 语义 = 恰好一个尾换行）
                if content.endswith(tuple(newline_set)):
                    content = content[:-1]
                return (content, pos, rule.token_type)

        return None
