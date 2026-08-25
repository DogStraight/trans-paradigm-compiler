"""capture_runner.py — 配置驱动的原始文本捕获扫描器（CaptureRunner）

抽象原语：从当前字符开始"原样捕获"一段文本（不做 token 化），按终止
条件结束，产出一个 token。注释（行/块）是 capture mode 表中的一个实例；
heredoc/围栏代码块/三引号字符串等同类构造均可作为配置项加入——引擎
不再硬编码任何"捕获类"语言知识（原 CommentRunner 只服务注释，本类为
其泛化，见 docs/known_limitations.md 的 lexer 原始捕获模式边界）。

配置面（token_define 两段，build_rules 归一化合并）：
1. [comment] pairs（legacy 兼容，三个语言包现有声明零改动）：
   pairs = [["#", "\\n", "line"], ["/*", "*/", "block"]]
   → kind "line" 终止于换行字符集；kind "block" 终止于 end 标记；
     token_type 固定为 "comment"。
2. [capture] 段（新，语言包按需声明）：
   [[capture]]
   start = "<<EOF"
   end = "EOF"
   kind = "line_match"
   token_type = "literal.heredoc"

kind 语义（终止条件）：
- "line"      : 到换行字符（[newline] 段配置，不硬编码 \\n）或 EOF；
                换行字符不消费（留给主循环）
- "marker"    : 到 end 标记（消费）或 EOF（未闭合自然终止）
- "line_match": 到"一行恰好等于 end"处（heredoc/围栏：`<<EOF ... EOF`
                终止于独立成行的 EOF）；end 后的换行不消费

多行捕获的行号记账由调用方（main_lexer）处理（与既有 comment 分支一致）。

Doc: docs/language_walkthrough.md（注释 token 扫描）
"""

from __future__ import annotations


class CaptureRule:
    """一种原始捕获模式的匹配规则。"""

    def __init__(self, start: str, end: str, kind: str, token_type: str):
        self.start = start  # 触发标记，如 "#" / "<<EOF"
        self.end = end  # 终止标记（marker/line_match 用；line 忽略）
        self.kind = kind  # "line" | "marker" | "line_match"
        self.token_type = token_type  # 产出 token 类型，如 "comment"
        self.start_len = len(start)
        self.end_len = len(end)


_VALID_KINDS = ("line", "marker", "line_match")


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

        # 2. 新 [capture] 段（TOML 数组表 [[capture]] → dict 列表）
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
                if kind != "line" and not mode.get("end"):
                    raise ValueError(
                        "[lexer] [capture] 段配置不完整："
                        f"kind={kind!r} 需要非空 end 终止标记，mode={mode!r}"
                    )
                rules.append(
                    CaptureRule(
                        start=str(mode["start"]),
                        end=str(mode.get("end", "")),
                        kind=kind,
                        token_type=str(token_type),
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
        text: str, start: int, token_define: dict
    ) -> tuple[str, int, str] | None:
        """从 start 位置尝试匹配任意 capture mode。

        Returns:
            (content, end_pos, token_type) — 捕获内容、结束位置（消费到的
            下标，不含换行终止符）、产出 token 类型
            None — 当前位置不匹配任何 mode
        """
        rules = CaptureRunner.build_rules(token_define)
        newline_set = set(token_define.get("newline", {}).values())
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

        return None
