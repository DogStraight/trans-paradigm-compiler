"""unit_graph.py — 文件级单元图（多入口 ⇒ 多根森林）。

定位：把"谁依赖谁"从各阶段事实收成一张图，供报告 / 后续 LSP 消费。图里**不放
语言语义**（端口/方向/精化产物仍在语言包 postpass）；节点 = 规范化绝对路径；
边 = `(kind, source, target)`，`kind` 是**引擎注册的能力面词汇**（能力 `unit_graph.edges.v1`），
不是语言包配置里的原始词：
- `instantiation`：单元实例化边（`structure` 阶段产）；
- `include`：文件包含边（`preprocessor` 阶段产）。
语言包只在 `[unit_graph] edge_kinds` 声明"产出哪些种类"；规则名/指令关键字属发现期数据，
不进图词汇（换语言不改变消费者契约）。

API 对齐通用工具链的「三问」（BSP `sources`/`inverseSources`、Meson
`target_sources`/`depends` 同构；见 `docs/references.md`「通用工具链的图化抽象」）：
- `roots`：本次 check 的入口集（**多入口 = 多根**）；
- `dependencies(root)`：该根直达的文件集；
- `inverse(path)`：哪些根能到达该文件（反查）。

多入口 ⇒ **多根森林**：共享节点只出现一次，`inverse` 返回多个 root 是合法结果。
Doc: docs/gaps/gap-unit-graph.md（块 5 契约与判据）
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.config_registry import declare_cfg
from core.errors import ConfigError

UnitEdgeTuple = tuple[str, str, str]

#: 图化**边种类注册表**（引擎能力面 `unit_graph.edges.v1`）。
#: 语言包只在 `[unit_graph] edge_kinds` 里声明"本包产出哪些种类"；引擎把各阶段的
#: 原始标签（`[structure] module_inst_rule` 的规则名、`[directive_handlers]` 的指令
#: 关键字）映射成这些**稳定 kind**——换语言时游戏规则不变，消费者只认这里。
EDGE_KINDS: dict[str, str] = {
    "instantiation": "structure",   # 单元实例化边（结构发现阶段产）
    "include": "preprocessor",      # 文件包含边（预处理器产）
}

_unit_graph_kinds: list = declare_cfg(
    "unit_graph.edge_kinds", [], __name__, "_unit_graph_kinds"
)
"""语言包声明的边种类集合（`[unit_graph] edge_kinds`）；未声明 = 不产边。"""


def norm_node(path: str) -> str:
    """节点身份唯一化：一次定型（绝对路径 + normcase）。

    Ninja 的教训（`docs/references.md`）：绝对/相对路径混用会被当成不同文件；
    图里统一定型，避免同一文件出现两个节点。
    """
    return os.path.normcase(os.path.abspath(path))


@dataclass(frozen=True)
class UnitEdge:
    """一条依赖边。`kind` 来自配置数据（规则名 / 指令关键字），不是引擎字面量。"""

    kind: str
    source: str
    target: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "source": self.source, "target": self.target}


class UnitGraph:
    """文件级依赖图（多根森林，节点/边去重）。

    Args:
        roots: 入口文件（顺序保留；重复入口去重）。
        edges: `(kind, source, target)` 三元组（路径可为相对/绝对，构造时统一规范化）。
        definitions: 可选，`{单元名: 定义文件}`（引擎 `module_index` 的同键视图；精化
            基座按它枚举单元原子/取定义文件，见 `analyzer/elaboration/`）。
    """

    def __init__(
        self,
        roots: list[str],
        edges: list[UnitEdgeTuple],
        definitions: dict[str, str] | None = None,
    ) -> None:
        self.roots: list[str] = list(dict.fromkeys(norm_node(r) for r in roots))
        self.definitions: dict[str, str] = {
            name: norm_node(path) for name, path in (definitions or {}).items()
        }
        self.edges: list[UnitEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for kind, source, target in edges:
            src, dst = norm_node(source), norm_node(target)
            if src == dst:
                continue  # 自环无信息（定义与实例化同文件）
            key = (kind, src, dst)
            if key in seen:
                continue
            seen.add(key)
            self.edges.append(UnitEdge(kind, src, dst))
        endpoints = [p for e in self.edges for p in (e.source, e.target)]
        self.nodes: list[str] = list(dict.fromkeys([*self.roots, *endpoints]))
        self._adj: dict[str, list[str]] = {}
        for edge in self.edges:
            self._adj.setdefault(edge.source, []).append(edge.target)

    def dependencies(self, root: str) -> list[str]:
        """该根直达的文件集（无向外的边 = 空表）。"""
        return list(self._adj.get(norm_node(root), []))

    def reachable(self, root: str) -> set[str]:
        """该根传递可达的文件集（含根自身）。"""
        start = norm_node(root)
        seen = {start}
        stack = [start]
        while stack:
            for nxt in self._adj.get(stack.pop(), []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def inverse(self, path: str) -> list[str]:
        """反查：哪些根能到达该文件（顺序 = roots 顺序）。"""
        target = norm_node(path)
        return [root for root in self.roots if target in self.reachable(root)]

    def to_dict(self) -> dict:
        """机器可读出口（`tpc check --json` 的 `graph` 字段）。"""
        return {
            "roots": list(self.roots),
            "nodes": list(self.nodes),
            "edges": [e.to_dict() for e in self.edges],
            "definitions": dict(self.definitions),
        }

    # ── 文本树出口（`tpc check --tree`） ──

    def render_tree(self) -> str:
        """多根森林 → 文本树（不依赖图形库；适合终端/日志/评审贴图）。

        形状：每个根一棵树，子节点带边 kind；重复节点第二次出现时标 `(seen)` 且不再展开
        （处理 diamond / 环；根本身不会重复展开）；单元定义以括号后缀标出。
        """
        lines: list[str] = []
        seen: set[str] = set()
        for root in self.roots:
            lines.append(f"● {self._caption(root)}  [root]")
            seen.add(root)
            self._render_children(root, "", seen, lines)
        return "\n".join(lines) if lines else "(empty graph)"

    def _render_children(self, path: str, prefix: str, seen: set[str], lines: list[str]) -> None:
        """递归展开一层子节点（连线/缩进；seen 去重后不再展开）。"""
        children = [(e.kind, e.target) for e in self.edges if e.source == path]
        for i, (kind, target) in enumerate(children):
            last = i == len(children) - 1
            branch = "└─ " if last else "├─ "
            line = f"{prefix}{branch}[{kind}] {self._caption(target)}"
            if target in seen:
                lines.append(line + "  (seen)")
                continue
            lines.append(line)
            seen.add(target)
            self._render_children(target, prefix + ("    " if last else "│   "), seen, lines)

    def _caption(self, path: str) -> str:
        """节点短名 + 单元定义后缀（无定义 → 仅文件名）。"""
        units = [u for u, f in self.definitions.items() if f == norm_node(path)]
        suffix = f"  ({', '.join(units)})" if units else ""
        return f"{os.path.basename(path)}{suffix}"

    @classmethod
    def from_dict(cls, data: dict) -> "UnitGraph":
        """`report["graph"]`（`to_dict()` 的逆）→ 图对象（CLI/测试消费用）。"""
        edges = [(e["kind"], e["source"], e["target"]) for e in data.get("edges") or []]
        return cls(
            list(data.get("roots") or []),
            edges,
            dict(data.get("definitions") or {}),
        )


def build_unit_graph(ctx, roots: list[str]) -> UnitGraph:
    """从会话事实装配图——**边由各阶段产，本函数只映射成注册 kind 并装配**。

    边种类由语言包 `[unit_graph] edge_kinds` 声明（能力面 `unit_graph.edges.v1`），
    引擎按 `EDGE_KINDS` 把"哪些阶段产哪种边"映射成稳定 kind；未注册的 kind 直接
    fail-fast（防语言包自造词汇、消费者失配）。

    Args:
        ctx: `StructureCtx`（含 `unit_edges` 单元依赖边、`memo` 里各文件的
            `include_edges` 包含边）。
        roots: 入口文件绝对路径列表。
    """
    declared = {str(k) for k in (_unit_graph_kinds or [])}
    unknown = declared - set(EDGE_KINDS)
    if unknown:
        raise ConfigError(
            f"[unit_graph] edge_kinds 含未注册的边种类 {sorted(unknown)}；"
            f"已注册: {', '.join(sorted(EDGE_KINDS))}（能力面 unit_graph.edges.v1）"
        )
    tuples: list[UnitEdgeTuple] = []
    for kind in sorted(declared):
        producer = EDGE_KINDS[kind]
        if producer == "structure":
            tuples.extend((kind, source, target) for source, target in ctx.unit_edges)
        elif producer == "preprocessor":
            tuples.extend(
                (kind, source, target)
                for fr in ctx.memo.values()
                for source, target in fr.include_edges
            )
    # 单元定义索引（name → 定义文件）：精化基座据此枚举单元原子（与 `module_index` 同键）
    definitions = {name: info.file for name, info in ctx.module_index.items()}
    return UnitGraph(roots, tuples, definitions)
