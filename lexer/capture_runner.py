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

from dataclasses import dataclass


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


@dataclass(frozen=True)
class _CaptureCtx:
    """一次捕获扫描的输入上下文（同一文本上跨 rule 复用）。"""

    text: str  # 输入文本
    start: int  # 触发位置（start 标记起始下标）
    newline_set: frozenset[str]  # [newline] 段声明的换行字符
    space_set: frozenset[str]  # [space] 段声明的空白字符
    base_col: int  # 触发行的物理缩进列（indent_leq 终止基准）


def _capture_line(
    ctx: _CaptureCtx, rule: CaptureRule, pos: int
) -> tuple[str, int, str]:
    """到换行字符（[newline] 段配置，不硬编码 \\n）或 EOF；换行不消费。"""
    text = ctx.text
    content = text[ctx.start:pos]
    while pos < len(text) and text[pos] not in ctx.newline_set:
        content += text[pos]
        pos += 1
    return (content, pos, rule.token_type)


def _capture_marker(
    ctx: _CaptureCtx, rule: CaptureRule, pos: int
) -> tuple[str, int, str]:
    """到 end 标记（消费）或 EOF（未闭合自然终止）。"""
    text = ctx.text
    content = text[ctx.start:pos]
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
    if content.endswith(tuple(ctx.newline_set)):
        content = content[:-1]
    return (content, pos, rule.token_type)


def _capture_delim(
    ctx: _CaptureCtx, rule: CaptureRule, pos: int
) -> tuple[str, int, str]:
    """到 end 定界符（消费，含定界符本身）或换行（不消费，不跨行）或 EOF。

    end 按**长度**比较（与 marker/line_match 同构）：此前用 `ch == rule.end`
    单字符比较，多字符定界符（如三引号）永不匹配 → 静默吞到行尾/EOF（把后续
    token 一起吃掉）。
    """
    text = ctx.text
    content = text[ctx.start:pos]
    end_len = rule.end_len
    while pos < len(text):
        if text[pos : pos + end_len] == rule.end:
            content += rule.end
            pos += end_len
            return (content, pos, rule.token_type)
        if text[pos] in ctx.newline_set:
            return (content, pos, rule.token_type)
        content += text[pos]
        pos += 1
    return (content, pos, rule.token_type)


def _capture_line_match(
    ctx: _CaptureCtx, rule: CaptureRule, pos: int
) -> tuple[str, int, str]:
    """到"一行恰好等于 end"处（heredoc/围栏）；end 后的换行不消费。"""
    text = ctx.text
    content = text[ctx.start:pos]
    while pos < len(text):
        if text[pos : pos + rule.end_len] == rule.end:
            # 前置必须是行首（pos 处是行起点）或换行后紧邻
            at_line_start = (
                pos == ctx.start + rule.start_len or text[pos - 1] in ctx.newline_set
            )
            after = pos + rule.end_len
            if at_line_start and (
                after >= len(text) or text[after] in ctx.newline_set
            ):
                return (content, pos, rule.token_type)
        content += text[pos]
        pos += 1
    return (content, pos, rule.token_type)


def _consume_indicator_line(ctx: _CaptureCtx, pos: int, content: str) -> tuple[str, int]:
    """指示符行（start → 行尾含换行）原样入 content → (content, 新 pos)。

    缩进指示/切块指示（|-/|+/|2）原样保留（与指示符行一体捕获，不做语义展开）。
    """
    text = ctx.text
    while pos < len(text) and text[pos] not in ctx.newline_set:
        content += text[pos]
        pos += 1
    if pos < len(text):  # 指示符行换行
        content += text[pos]
        pos += 1
    return content, pos


def _scalar_line_bounds(ctx: _CaptureCtx, pos: int) -> tuple[int, int, int]:
    """内容行 → (行首, 行尾（不含换行）, 物理列)。

    行首空白 → 物理列（tab 计 1 列，宽容）。
    """
    text = ctx.text
    line_start = pos
    p = pos
    while p < len(text) and text[p] in ctx.space_set:
        p += 1
    eol = p
    while eol < len(text) and text[eol] not in ctx.newline_set:
        eol += 1
    return line_start, eol, p - line_start


def _capture_indent_leq(
    ctx: _CaptureCtx, rule: CaptureRule, pos: int
) -> tuple[str, int, str]:
    """YAML 块标量：逐行捕获"列 > base_col"的内容行。

    指示符行（start → 行尾含换行）原样入 content，然后逐行捕获
    "列 > base_col"的内容行（含空行——空行是内容），遇"非空且列 ≤ base_col"
    的行终止（该行不消费）。终止基准 = 触发行的物理缩进列（base_col，由
    lexer 传入行首空白宽度）。
    """
    text = ctx.text
    content = text[ctx.start:pos]
    content, pos = _consume_indicator_line(ctx, pos, content)
    while pos < len(text):
        line_start, eol, col = _scalar_line_bounds(ctx, pos)
        if eol > line_start + col and col <= ctx.base_col:
            break  # 终止行（非空、列 ≤ 基准）：不消费
        # 内容行（含空行）：整行含换行入 content
        if eol < len(text):
            eol += 1  # 含换行
        content += text[line_start:eol]
        pos = eol
    # 剥一个尾部换行：渲染时节点间 join "\n" 恰好补回，避免
    # 输出空行（字面块 clip 语义 = 恰好一个尾换行）
    if content.endswith(tuple(ctx.newline_set)):
        content = content[:-1]
    return (content, pos, rule.token_type)


# kind → 终止条件 handler（`_VALID_KINDS` 由本表派生，保证两者不脱节）
_CAPTURE_HANDLERS = {
    "line": _capture_line,
    "marker": _capture_marker,
    "delim": _capture_delim,
    "line_match": _capture_line_match,
    "indent_leq": _capture_indent_leq,
}

_VALID_KINDS = tuple(_CAPTURE_HANDLERS)


def _legacy_comment_rule(item) -> CaptureRule | None:
    """legacy `[comment] pairs` 单项 → 规则（条目过短 → None）。

    kind "block" 归一化为 "marker"；未知 kind fail-fast（decisions/0003）。
    """
    if len(item) >= 3:
        start, end, legacy_kind = item[0], item[1], item[2]
    elif len(item) == 2:
        start, end = item[0], item[1]
        legacy_kind = "line"
    else:
        return None
    kind = "marker" if legacy_kind == "block" else legacy_kind
    if kind not in _VALID_KINDS:
        raise ValueError(
            "[lexer] [comment] pairs 含未知 kind: "
            f"{legacy_kind!r}（合法: line / block）"
        )
    return CaptureRule(start, end, kind, "comment")


def _legacy_comment_rules(token_define: dict) -> list[CaptureRule]:
    """legacy `[comment] pairs` → token_type = "comment"。"""
    rules: list[CaptureRule] = []
    for item in token_define.get("comment", {}).get("pairs", []):
        rule = _legacy_comment_rule(item)
        if rule is not None:
            rules.append(rule)
    return rules


def _string_delim_rules(token_define: dict) -> list[CaptureRule]:
    """`[string] delimiters` → kind "delim" / token_type "literal.string"。

    引擎不再硬编码引号定界符（verilog 只声明 "，yaml/c4 声明 " 与 '）。
    """
    rules: list[CaptureRule] = []
    for delim in token_define.get("string", {}).get("delimiters", []) or []:
        if not isinstance(delim, str) or not delim:
            raise ValueError(
                "[lexer] [string] delimiters 含非法条目: "
                f"{delim!r}（须为非空字符串）"
            )
        rules.append(CaptureRule(delim, delim, "delim", "literal.string"))
    return rules


def _capture_rule_from_mode(mode: dict) -> CaptureRule:
    """单个 `[[capture]]` 条目 → 规则（配置不完整 → fail-fast）。"""
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
    return CaptureRule(
        start=str(mode["start"]),
        end=str(mode.get("end", "")),
        kind=kind,
        token_type=str(token_type),
        after=tuple(str(t) for t in after),
        next_chars=str(mode.get("next_chars", "")),
    )


def _capture_section_rules(token_define: dict) -> list[CaptureRule]:
    """新 `[[capture]]` 段（TOML 数组表 → dict 列表）→ 规则。"""
    modes = token_define.get("capture")
    if not isinstance(modes, list):
        return []
    rules: list[CaptureRule] = []
    for mode in modes:
        if isinstance(mode, dict):
            rules.append(_capture_rule_from_mode(mode))
    return rules


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
        各段细则见 `_legacy_comment_rules` / `_string_delim_rules` /
        `_capture_section_rules`。
        """
        rules = (
            _legacy_comment_rules(token_define)
            + _string_delim_rules(token_define)
            + _capture_section_rules(token_define)
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

        扫描本体按 kind 分派到 `_CAPTURE_HANDLERS`（每个 handler 一种终止
        条件，见各 handler docstring）；本方法只做触发判定与上下文装配。
        """
        rules = CaptureRunner.build_rules(token_define)
        ctx = _CaptureCtx(
            text=text,
            start=start,
            newline_set=frozenset(token_define.get("newline", {}).values()),
            space_set=frozenset(token_define.get("space", {}).values()),
            base_col=base_col,
        )
        for rule in rules:
            # 检查是否以起始标记开头
            if text[start : start + rule.start_len] != rule.start:
                continue
            pos = start + rule.start_len
            return _CAPTURE_HANDLERS[rule.kind](ctx, rule, pos)
        return None

