"""
comment_fsm.py — 注释剥离有限状态机

将注释解析从主词法分析器中抽离，作为独立阶段。
支持行注释 // 和块注释 /* */ ，注释边界符由 _token.toml 的 [comment] 段配置。

用法:
    token_def = {...}  # 从 _token.toml 加载的合并字典
    result = CommentFSM.run(source_text, start_index, token_def)
    if result:
        content, end_pos = result  # content 包含注释原文 + 终止符
"""

from typing import Optional, Tuple


class CommentFSM:
    """基于 GenericFSM 模式的注释解析器"""

    # 状态常量
    INIT = 0           # 初始，等待边界符
    SEEN_BOUNDARY = 1  # 已见一个边界符，判断是 // 还是 /*
    LINE = 2           # 行注释中 // ...
    BLOCK = 3          # 块注释中 /* ...
    BLOCK_STAR = 4     # 块注释中遇到 *，准备闭合

    @staticmethod
    def run(
        text: str, start: int, token_define: dict
    ) -> Optional[Tuple[str, int]]:
        """尝试从 start 位置解析注释

        Args:
            text: 源文本
            start: 当前解析位置
            token_define: 合并后的 token 定义字典（含 [comment]）

        Returns:
            (content, end_pos)  注释原文 + 结束位置（不含终止符）
            None                当前位置不是注释
        """
        # 获取注释边界符（默认为 "/"）
        comment_cfg = token_define.get("comment", {})
        boundaries = comment_cfg.get("boundary", "/")
        # 支持多字符边界符列表或单个字符
        if isinstance(boundaries, str):
            boundaries = [boundaries]

        if start >= len(text):
            return None
        if text[start] not in boundaries:
            return None

        # 启动 FSM
        state = CommentFSM.SEEN_BOUNDARY
        pos = start + 1
        content = text[start]

        while pos < len(text):
            ch = text[pos]

            if state == CommentFSM.SEEN_BOUNDARY:
                if ch in boundaries:
                    # // 行注释
                    state = CommentFSM.LINE
                    content += ch
                    pos += 1
                elif ch == "*":
                    # /* 块注释
                    state = CommentFSM.BLOCK
                    content += ch
                    pos += 1
                else:
                    # 不是注释（单独的 / 不是注释边界）
                    return None

            elif state == CommentFSM.LINE:
                # 行注释：直到换行（不含 \n 本身）
                if ch == "\n":
                    pos += 1
                    break
                content += ch
                pos += 1

            elif state == CommentFSM.BLOCK:
                if ch == "*":
                    state = CommentFSM.BLOCK_STAR
                content += ch
                pos += 1

            elif state == CommentFSM.BLOCK_STAR:
                if ch == "/":
                    content += ch
                    pos += 1
                    break
                elif ch == "*":
                    content += ch
                    pos += 1
                    # 保持 BLOCK_STAR 状态
                else:
                    state = CommentFSM.BLOCK
                    content += ch
                    pos += 1

        return (content, pos)
