"""node.py — 结构层产物：发现节点与上下文标记。

发现层（`structure/discovery.py`）把 token 流变形成"轻量 AST"——`DiscoveredNode`
只记录"发现了什么语法（rule）/ 在哪个 token 区间（start,end）/ 属于什么上下文
（context）/ 子结构（children）"，不含属性绑定与符号表。linter 与 islands 都消费
这一形态：前者按节点注册检查器，后者把节点当分片候选。

`UnrecognizedSite` 是发现层的**中立记录**：有语句起点特征但没有任何规则匹配的
token 位置 + 说明。linter 把它转成 `phase-unrecognized` 诊断，islands 把它当 water
（不承诺语义）。结构层不依赖 linter 的诊断类型。

Doc: structure/README.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 顶层上下文（发现入口）：块内上下文名不参与候选筛选（B 类 ident 候选是单一全局
# 集合，靠 Level 1 前瞻 / Level 2 试解析精确筛选），context 仅作节点归属标记
CTX_TOP = "top"


@dataclass
class DiscoveredNode:
    """轻量 AST 节点 — 发现阶段的产物。"""

    type: str              # "bound" | "statement" | "token"
    rule: "str | list[str]"  # 同一起始 token 的多个候选规则（如 TaskDeclANSI/Old）
    start: int
    end: int
    context: str = CTX_TOP
    children: list["DiscoveredNode"] = field(default_factory=list)


@dataclass(frozen=True)
class UnrecognizedSite:
    """未识别语句位点（token 索引 + 说明）；消费方自行决定诊断或 water。"""

    start: int
    message: str
