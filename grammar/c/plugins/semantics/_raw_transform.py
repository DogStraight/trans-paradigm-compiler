"""_raw_transform.py — P4 理解路径 · **transform 段「改树」**（C 包）。

作者定调的两段协作第二段：**改树 = 变换插件流程**——按 analyzer 段（`_raw_understand.py`）
的结论执行改树。本段只做**机械提升**，不重新判定语义（结论已在 analyze 期由 P4 校验 +
理解段给出；无结论的 raw 节点不动）。

提升方式：`raw_node.sub_node = [raw_candidate]`，**保留** `_verbatim_text`（渲染仍直出 ⇒
保真不回归）、`raw_names`/`raw_line`/`raw_column`/`raw_order`/`raw_substituted`/`raw_candidate`
（取证与非预期变化面可查）。**契约 A3 的有意升级**：承载期 `sub_node == []`；提升后
raw 节点带子节点（不变式见 `grammar/c/README.md`：渲染权威 = `_verbatim_text`；子树只是
分析的确定结构，其显著 token 序列须与 verbatim 等价）。

**重复产出/重复处理（方案 F17 确认点）**：`Node.iter_children()` 含**属性挂载**的子节点，
故候选在承载期就能被遍历到（`raw_candidate` 属性）；提升后候选同时出现在 `sub_node` 与
`raw_candidate` 里，`iter_children()` 按 `id` 去重（`core/define.py:234-251`）⇒ 遍历**恰好
一次**，不重复产出。本插件自身按 `sub_node` 是否为空判幂等（二次运行零改动）。
Doc: `grammar/c/README.md`「P4 理解路径（两段协作）」
"""
from __future__ import annotations

from typing import Any

from core.define import CHILDREN_FIELD, Node, iter_nodes
from analyzer.raw_contract import RAW_STATEMENT_NODE_NAME
from transform.engine import TransformPlugin, register_plugin
from grammar.c.plugins.semantics._raw_understand import (
    CANDIDATE_ATTR,
    UNDERSTAND_ATTR,
)


@register_plugin(name="c.raw_promote")
class RawPromotePlugin(TransformPlugin):
    """把带理解结论的 raw 节点提升为确定结构（`sub_node = [raw_candidate]`）。"""

    def process(self, ast: Node, root_scope: Any) -> Node:
        del root_scope  # 本段不需要符号面（结论已由 analyzer 段落档）
        promoted = 0
        for node in iter_nodes(ast):
            if node.node_name != RAW_STATEMENT_NODE_NAME:
                continue
            if getattr(node, CHILDREN_FIELD, None):
                continue  # 幂等：已提升（或承载期本就带子节点）⇒ 不动
            conclusion = getattr(node, UNDERSTAND_ATTR, None)
            candidate = getattr(node, CANDIDATE_ATTR, None)
            if not isinstance(conclusion, dict) or not conclusion.get("ok"):
                continue  # 无理解结论 ⇒ 不提升（raw 仍走 verbatim 直出）
            if not isinstance(candidate, Node):
                continue  # 结论在而候选不在 = 不该发生；保守不提升（不静默产出坏结构）
            node.add_attr(CHILDREN_FIELD, [candidate])
            promoted += 1
        self._promoted = promoted
        return ast

    @property
    def stats(self) -> dict[str, int]:
        return {"raw_promoted": getattr(self, "_promoted", 0)}
