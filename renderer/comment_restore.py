"""comment_restore.py — tpc 还原编排（marker 回插 + 宏/条件块还原；
C3 重构，2026-08-28）。

从 pipeline/__init__.py 拆出：tpc 还原（inline/line marker 回插 + 宏还原 +
条件块）的决策编排是 renderer 职责——pipeline 只做 ctx 取值和调用。参数
显式化后成为可独立测试的纯函数（log_fn 回调注入，不依赖 pipeline 上下文对象）。

Doc: renderer/renderer_architecture.md（注释单机制：restore 纯 tpc）
"""

from typing import Any, Callable

from preprocessor._reverse import protect_and_reverse, restore_condition_blocks
from .inline_comment import restore_comments, restore_line_comments


def restore_all_comments(
    content: str,
    *,
    comment_anchors: list | None,
    line_anchors: list | None,
    restoration_stack: Any | None,
    placeholders: dict | None,
    tpc_src_map: dict | None,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """tpc 还原编排（marker 回插 + 宏还原 + 条件块）。

    参数为 pipeline 上下文的显式投影（C3 重构）——决策逻辑与 pipeline 解耦：
    - comment_anchors/line_anchors: parser 收集的锚点列表
    - restoration_stack: 宏展开还原栈（非空 = 展开路径）
    - placeholders: 条件块占位映射
    - tpc_src_map: 源行号 → 渲染行号插值锚点
    - log_fn: 日志回调（默认静默）

    注：普通注释回插通道已全部删除（ADR-0013 单机制——注释进树结构序
    渲染，不再时域回插）：
      - inline 通道仅剩展开路径 only_tpc（marker 回插，宏还原依赖）；
        非展开路径行中注释由 renderer 布局锚消费渲染（line.py 文本/ref
        锚 + join 分隔符锚，ADR-0013 ③），midline 回插兜底实测纯冗余
        （normal 组禁用前后输出一致）——2026-09-05 删除；
      - line 通道仅剩 only_tpc（宏/条件块 marker 回插）——普通独占行
        注释全部进树（容器项间 Comment 迭代项 / 首元素前 Comment 子节点
        / 块结束符 trailing / block body Comment 节点），41 文件实测
        restore 开/关差仅 1 条且为锚点错插缺陷，删除净改善。
    """
    log = log_fn or (lambda _: None)
    restore_stack = bool(restoration_stack)

    # Inline comment restoration：仅展开路径——宏 marker（`/*<tpc:macro:N>*/`）
    # 是块注释，被 parse_token 收集进 _comment_anchors，不回注则
    # protect_and_reverse 找不到 marker 宏调用丢失（tv80 `TV80DELAY`）；
    # 普通注释锚点漂移（渲染行号与源行号错位）会错插到端口/参数行——普通
    # 注释进树结构序渲染，不在此回插（restore_comments 恒 tpc 语义）。
    if comment_anchors and restore_stack:
        content, n = restore_comments(
            content, comment_anchors, tpc_src_map=tpc_src_map
        )
        log(f"[comments] tpc inline marker restoration: {n} items")

    # Line comment restoration：恒 tpc 语义（见函数 docstring——普通独占行
    # 注释已全部进树，不再时域回插）。tpc marker（宏/条件块还原依赖）是
    # 唯一性插值定位、不依赖锚点窗口，仍必须回插——否则 protect_and_reverse
    # 找不到 marker，宏还原失效。有宏/条件块时回插，无则整个跳过。
    if line_anchors and (restore_stack or placeholders):
        content, n = restore_line_comments(
            content, line_anchors, tpc_src_map=tpc_src_map
        )
        log(f"[comments] tpc marker restoration: {n} items")

    # Reverse macro protection — 必须放在 line-comment restore 之后：
    # 宏 line 锚（`// <tpc:macro:N>`）是注释行，被 parser 收集进
    # line_comment_anchors，由 restore_line_comments 回插后 protect_and_reverse
    # 才能定位 marker 并替换为整行原文。
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
