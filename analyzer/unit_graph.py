"""unit_graph.py — 文件级单元图（多入口 ⇒ 多根森林）。

定位：把"谁依赖谁"从各阶段事实收成一张图，供报告 / 后续 LSP 消费。图里**不放
语言语义**（端口/方向/精化产物仍在语言包 postpass）；节点 = 规范化绝对路径；
边 = `(kind, source, target)`：`kind` 是**语言包自己的词汇**（语言侧抽象，随包携带；
能力面 `unit_graph.edges.v2` 的配置声明面）：

    [[unit_graph.edges]]
    kind = "instantiation"
    from = "structure.unit_edges"

引擎只保留**产边通道注册表** `EDGE_CHANNELS`（"从哪个阶段收边"是管线编排事实，不是
语言知识）；规则名/指令关键字属发现期数据，不进图词汇。消费者只把 `kind` 当标签，
所以 kind 词汇开放、通道封闭（新增通道才需改引擎）。

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
import re
from dataclasses import dataclass

from core.config_registry import declare_cfg
from core.errors import ConfigError

UnitEdgeTuple = tuple[str, str, str]

# ── 产边通道注册表（引擎**封闭面**：管线编排事实，不是语言知识）──
#: 每个通道 = `(ctx) -> Iterable[(source, target)]`（取边函数；不做第二遍解析）。
#: 语言包声明 `from = "<通道名>"` 只能选这里；新增通道才是引擎改动。


def _channel_structure_unit_edges(ctx):
    """结构发现阶段的口径：`ctx.unit_edges`（`ModuleIndexer.discover` 产）。"""
    return ctx.unit_edges


def _channel_preprocessor_include_edges(ctx):
    """预处理器口径：各文件 `FileResult.include_edges`（已解析绝对路径，无缺失）。"""
    return [
        (source, target)
        for fr in ctx.memo.values()
        for source, target in fr.include_edges
    ]


EDGE_CHANNELS: dict = {
    "structure.unit_edges": _channel_structure_unit_edges,
    "preprocessor.include_edges": _channel_preprocessor_include_edges,
}

_unit_graph_edges: list = declare_cfg(
    "unit_graph.edges", [], __name__, "_unit_graph_edges"
)
"""语言包边声明（`[[unit_graph.edges]] kind + from`）；未声明 = 不产边。"""

_legacy_edge_kinds: object = declare_cfg(
    "unit_graph.edge_kinds", None, __name__, "_legacy_edge_kinds"
)
"""旧键探测器：出现即 fail-fast 并指向新写法（不留兼容垫片）。"""

_EDGE_KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")


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


def _declared_edges() -> list[dict]:
    """读取并校验语言包边声明（`[[unit_graph.edges]]`）——fail-closed，不留兼容垫片。"""
    if _legacy_edge_kinds is not None:
        raise ConfigError(
            "[unit_graph] 旧键 edge_kinds 已移除：改用 [[unit_graph.edges]] kind + from"
            "（能力面 unit_graph.edges.v2）"
        )
    declared = _unit_graph_edges or []
    if not isinstance(declared, list):
        raise ConfigError(
            f"[unit_graph] edges 须为 [[unit_graph.edges]] 表列表，实得 {type(declared).__name__}"
        )
    channels = ", ".join(sorted(EDGE_CHANNELS))
    edges: list[dict] = []
    seen: set[str] = set()
    for entry in declared:
        if not isinstance(entry, dict):
            raise ConfigError(f"[unit_graph.edges] 每项须为表，实得 {entry!r}")
        extra = set(entry) - {"kind", "from"}
        if extra:
            raise ConfigError(f"[unit_graph.edges] 未知字段 {sorted(extra)}（只收 kind/from）")
        kind, source = entry.get("kind"), entry.get("from")
        if not isinstance(kind, str) or not _EDGE_KIND_RE.fullmatch(kind):
            raise ConfigError(
                f"[unit_graph.edges] kind 须匹配 ^[a-z][a-z0-9_]*$，实得 {kind!r}"
            )
        if kind in seen:
            raise ConfigError(f"[unit_graph.edges] kind 重复：{kind!r}（每 kind 只声明一次）")
        if source not in EDGE_CHANNELS:
            raise ConfigError(
                f"[unit_graph.edges] from 不在产边通道表：{source!r}；"
                f"已注册通道: {channels}（能力面 unit_graph.edges.v2）"
            )
        seen.add(kind)
        edges.append({"kind": kind, "from": source})
    return edges


def build_unit_graph(ctx, roots: list[str]) -> UnitGraph:
    """从会话事实装配图——**按语言包声明逐条取边**（引擎只认通道，不认 kind）。

    声明 = `[[unit_graph.edges]] kind + from`（能力面 `unit_graph.edges.v2`）：
    - `kind` 归语言包（语言侧抽象，消费者只当标签打印）；
    - `from` 只能选 `EDGE_CHANNELS` 的已注册通道；未知通道/重复 kind/非法命名/
      旧键 `edge_kinds` 均 fail-fast（报错自解释，不留兼容垫片）。

    Args:
        ctx: `StructureCtx`（含 `unit_edges` 单元依赖边、`memo` 里各文件的
            `include_edges` 包含边）。
        roots: 入口文件绝对路径列表。
    """
    tuples: list[UnitEdgeTuple] = []
    for edge in _declared_edges():
        gather = EDGE_CHANNELS[edge["from"]]
        tuples.extend((edge["kind"], source, target) for source, target in gather(ctx))
    # 单元定义索引（name → 定义文件）：精化基座据此枚举单元原子（与 `module_index` 同键）
    definitions = {name: info.file for name, info in ctx.module_index.items()}
    return UnitGraph(roots, tuples, definitions)
