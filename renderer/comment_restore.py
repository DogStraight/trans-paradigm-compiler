"""comment_restore.py — 注释回插编排（C3 重构，2026-08-28）。

从 pipeline/__init__.py 拆出：注释回插（inline + line + 宏还原 + 条件块）
的决策编排是 renderer 职责——pipeline 只做 ctx 取值和调用。参数显式化后
成为可独立测试的纯函数（log_fn 回调注入，不依赖 pipeline 上下文对象）。

Doc: docs/decisions/0006-renderer-improve-roadmap.md（注释 attachment 双轨）
"""

from typing import Any, Callable

from core.define import Node
from preprocessor._reverse import protect_and_reverse, restore_condition_blocks
from .inline_comment import restore_comments, restore_line_comments


def collect_inline_after_leftover(root: Any, anchors: list) -> None:
    """收集渲染后未消费的行中注释（注释节点模型 2b-2 兜底）。

    inline_after = {锚 token: [(注释, 源行号)]} 是 token 标注定位——渲染端
    在布局 line 文本元素里按锚文本匹配。布局无文本锚（如 pratt 表达式内
    `a + /* c */ b` 的 `+` 在 op 子节点）时渲染端不消费 → 此处补进 anchors
    （midline 标记），restore only_midline 回插兜底。已消费的（渲染端删了
    键）不补——双轨不双份。
    """
    if isinstance(root, Node):
        slots = getattr(root, "_comment_slots", None)
        if slots:
            ia = slots.get("inline_after")
            if ia:
                for anchor, entries in ia.items():
                    for text, line in entries:
                        anchors.append(
                            {
                                "anchor": anchor,
                                "text": text,
                                "line": line,
                                "midline": True,
                            }
                        )
                del slots["inline_after"]
        for k, v in list(vars(root).items()):
            if k.startswith("_"):
                continue
            collect_inline_after_leftover(v, anchors)
    elif isinstance(root, dict):
        for v in root.values():
            collect_inline_after_leftover(v, anchors)
    elif isinstance(root, list):
        for v in root:
            collect_inline_after_leftover(v, anchors)


def restore_all_comments(
    content: str,
    *,
    comment_anchors: list | None,
    line_anchors: list | None,
    restoration_stack: Any | None,
    placeholders: dict | None,
    tpc_src_map: dict | None,
    enable_line_comment_restore: bool | None,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """注释回插编排（inline + line + 宏还原 + 条件块）。

    参数为 pipeline 上下文的显式投影（C3 重构）——决策逻辑与 pipeline 解耦：
    - comment_anchors/line_anchors: parser 收集的锚点列表
    - restoration_stack: 宏展开还原栈（非空 = 展开路径）
    - placeholders: 条件块占位映射
    - tpc_src_map: 源行号 → 渲染行号插值锚点
    - enable_line_comment_restore: line 通道普通注释恢复开关（None = 关闭）
    - log_fn: 日志回调（默认静默）

    注：旧 `--inline-comments` 指纹回注开关已删除（2026-09-04，老机制不稳定
    且消耗大）——inline 通道仅两态：展开路径 only_tpc（marker 回插）、
    非展开 only_midline（行中注释回插兜底）。
    """
    log = log_fn or (lambda m: None)
    restore_stack = bool(restoration_stack)

    # Inline comment restoration（锚点匹配，宏展开后亦可用）
    # 展开路径（restore_stack 非空）→ only_tpc：宏 marker（`/*<tpc:macro:N>*/`）
    # 是块注释，被 parse_token 收集进 _comment_anchors，不回注则
    # protect_and_reverse 找不到 marker 宏调用丢失（tv80 `TV80DELAY`）；
    # 但普通注释锚点漂移（渲染行号与源行号错位）会错插到端口/参数行——
    # 只回插 tpc，普通注释跳过（与 line 通道 only_tpc 语义对称）。
    if not comment_anchors:
        pass
    elif restore_stack:
        content, n = restore_comments(
            content, comment_anchors, only_tpc=True, tpc_src_map=tpc_src_map
        )
        log(f"[comments] tpc inline marker restoration: {n} items")
    else:
        # 行中注释回插（P1.5）：行中块注释不挂 attachment（保持原位），
        # 无渲染兜底——回插防丢（行尾注释由 attachment 渲染，不在此列）。
        content, n = restore_comments(content, comment_anchors, only_midline=True)
        if n:
            log(f"[comments] midline anchor restoration: {n} items")

    # Line comment restoration（列表结构内被 production skip 吞掉的注释，渲染后回插）
    # 变换路径（expand_enhanced=True 增强展开）禁用普通注释恢复：变换改变
    # 了代码结构（impl → ModuleInst、类型端口 → 具体端口），源行号/锚点必然
    # 漂移，恢复会误匹配拆坏注释行（如含 `spi.slave` 的注释从 `.` 处劈开）。
    # 但 tpc marker（宏/条件块还原依赖）是唯一性插值定位、
    # 不依赖锚点窗口，仍必须回插——否则 protect_and_reverse 找不到 marker，
    # 宏还原失效。有宏/条件块时降级 only_tpc，无则整个跳过。
    if line_anchors and enable_line_comment_restore:
        content, n = restore_line_comments(
            content, line_anchors, tpc_src_map=tpc_src_map
        )
        log(f"[comments] line anchor restoration: {n} items")
    elif line_anchors and (restore_stack or placeholders):
        content, n = restore_line_comments(
            content, line_anchors, tpc_src_map=tpc_src_map, only_tpc=True
        )
        log(f"[comments] tpc marker restoration: {n} items")

    # Reverse macro protection — 必须放在 line-comment restore 之后：
    # 宏 line 锚（`// <tpc:macro:N>`）是注释行，被 parser 收集进
    # line_comment_anchors，由 restore_line_comments 回插后 protect_and_reverse
    # 才能定位 marker 并替换为整行原文残片。
    if restore_stack:
        content = protect_and_reverse(
            content, restoration_stack=restoration_stack
        )
        log("[preprocessor] macros reversed")

    # Restore conditional blocks（占位注释 → 原文，inactive 分支 + 块边界）
    # 必须放在 line-comment restore 之后：占位符 `// <tpc:cond:N>` 本身是注释行，
    # 可能被 production skip 吞掉并记入 line_comment_anchors，若先 restore 条件块、
    # 后回插行注释，占位符会被再次插回而残留。
    if placeholders:
        content = restore_condition_blocks(content, placeholders)
        log(f"[preprocessor] condition blocks restored: {len(placeholders)}")
    return content
