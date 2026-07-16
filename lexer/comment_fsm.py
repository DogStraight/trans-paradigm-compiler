"""
comment_fsm.py — 配置驱动的注释解析器

完全由 _token.toml 的 [comment] pairs 配置驱动：
    pairs = [
        ["//", "\\n", "line"],
        ["/*", "*/", "block"],
    ]
"""

from typing import Optional, Tuple, List


class CommentRule:
    """一种注释类型的匹配规则"""

    def __init__(self, start: str, end: str, kind: str):
        self.start = start  # 起始标记，如 "//"
        self.end = end  # 结束标记，如 "\\n" 或 "*/"
        self.kind = kind  # "line" | "block"
        self.start_len = len(start)
        self.end_len = len(end)


class CommentFSM:
    @staticmethod
    def build_rules(token_define: dict) -> List[CommentRule]:
        """从配置构建注释规则列表"""
        pairs = token_define.get("comment", {}).get("pairs", [])
        rules = []
        for item in pairs:
            if len(item) >= 3:
                start, end, kind = item[0], item[1], item[2]
            elif len(item) == 2:
                start, end = item
                kind = "line"
            else:
                continue
            rules.append(CommentRule(start, end, kind))
        # 按起始标记长度降序，避免短标记优先匹配（如 / 在 // 前）
        rules.sort(key=lambda r: -r.start_len)
        return rules

    @staticmethod
    def get_start_patterns(token_define: dict) -> List[str]:
        """获取所有注释起始标记，用于 lexer 预判断"""
        rules = CommentFSM.build_rules(token_define)
        return [r.start for r in rules]

    @staticmethod
    def run(
        text: str, start: int, token_define: dict
    ) -> Optional[Tuple[str, int, str]]:
        """从 start 位置尝试匹配任意注释类型

        Returns:
            (content, end_pos, kind) — 注释内容、结束位置、类型
            None — 当前位置不是注释
        """
        rules = CommentFSM.build_rules(token_define)
        for rule in rules:
            # 检查是否以起始标记开头
            if text[start : start + rule.start_len] != rule.start:
                continue

            pos = start + rule.start_len
            content = text[start:pos]

            if rule.kind == "line":
                # 行注释：直到 \n 或文件末尾，不消费 \n
                while pos < len(text) and text[pos] != "\n":
                    content += text[pos]
                    pos += 1
                return (content, pos, "line")

            elif rule.kind == "block":
                # 块注释：直到结束标记
                while pos < len(text):
                    if text[pos : pos + rule.end_len] == rule.end:
                        content += text[pos : pos + rule.end_len]
                        pos += rule.end_len
                        return (content, pos, "block")
                    content += text[pos]
                    pos += 1
                # 文件未闭合块注释
                return (content, pos, "block")

        return None
