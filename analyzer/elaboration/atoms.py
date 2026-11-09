"""atoms.py — 引擎侧原子供源：文件 / 单元 / 工程（**零语言知识**）。

"单元"的判定走**声明**（`[structure]` 的单元规则名 + 单元名字段），引擎不认
"模块"；未声明单元规则 → 不产生单元原子（该语言包不做单元级精化）。

**块 6（图化）**：传入 `UnitGraph` 时，文件原子 = 图节点、单元原子 = 图定义索引
（`graph.definitions`）——精化基座只消费图，不再自行扫 `memo` / `collect_nodes`；
未传图 = 旧的会话直读（兼容测试/降级路径）。

原子键的选定：
- `unit` → **单元名**（与既有 `module_index` 同键，行为对齐，便于过渡期对拍）；
- `file` → 文件路径；
- `project` → 单原子（键 = `""`）。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from core.define import Node, collect_nodes

from analyzer.elaboration.contract import SCOPE_FILE, SCOPE_PROJECT, SCOPE_UNIT
from analyzer.elaboration.driver import Atom


class _SessionLike(Protocol):
    """引擎会话里本供源需要的那几样（结构上满足 `StructureCtx`）。"""

    @property
    def memo(self) -> Mapping[str, Any]:
        """本次运行已发现的文件（路径 → FileResult）。"""
        ...

    @property
    def module_index(self) -> Mapping[str, Any]:
        """单元名 → 单元条目（有 `node` / `file`；图定义索引取节点用）。"""
        ...

    def rule(self, key: str) -> str:
        """规则名类声明项（如单元声明规则）。"""
        ...

    def field(self, key: str) -> str:
        """节点字段名类声明项（如单元名字段）。"""
        ...


class StructureAtomSource:
    """按会话状态（可选：按单元图）枚举原子。

    Args:
        ctx: 会话状态（`memo` / `module_index` / 声明面）。
        graph: 单元图（块 6 起由 `ProjectChecker` 传入）——文件原子取图节点、
            单元原子取图定义索引；`None` = 直读会话（兼容/降级）。
    """

    def __init__(self, ctx: _SessionLike, graph: Any = None) -> None:
        self._ctx = ctx
        self._graph = graph

    def atoms(self, scope: str) -> list[Atom]:
        if scope == SCOPE_PROJECT:
            return [Atom(key="", node=None)]
        out: list[Atom] = []
        if self._graph is not None:
            if scope == SCOPE_UNIT:
                return self._units_from_graph()
            # 图节点是规范化的（normcase/abspath），memo 键保留原始大小写/相对形态；
            # 原子键仍用 memo 原路径（行为对齐），只按规范化身份做匹配。
            from analyzer.unit_graph import norm_node

            memo_by_norm = {norm_node(p): p for p in self._ctx.memo}
            for node in self._graph.nodes:
                real = memo_by_norm.get(node)
                if real is None:
                    continue
                fr = self._ctx.memo[real]
                out.append(Atom(key=real, path=real, node=fr.ast))
            return out
        for path, fr in self._ctx.memo.items():
            if scope == SCOPE_FILE:
                out.append(Atom(key=path, path=path, node=fr.ast))
            elif scope == SCOPE_UNIT:
                out.extend(self._units_of(path, fr.ast))
        return out

    # ── 单元枚举（图定义索引；节点从会话索引取） ──

    def _units_from_graph(self) -> list[Atom]:
        out: list[Atom] = []
        for name, path in self._graph.definitions.items():
            info = self._ctx.module_index.get(name)
            node = getattr(info, "node", None) if info is not None else None
            out.append(Atom(key=name, path=path, node=node))
        return out

    # ── 单元枚举（走声明） ──

    def _units_of(self, path: str, ast: Node | None) -> list[Atom]:
        rule = self._ctx.rule("module_decl_rule")
        if not rule or ast is None:
            return []
        name_field = self._ctx.field("module_name")
        return [
            Atom(key=self._unit_name(node, name_field), path=path, node=node)
            for node in collect_nodes(ast, rule)
        ]

    @staticmethod
    def _unit_name(node: Node, name_field: str) -> str:
        """单元名（字段名来自声明；取不到 → 空串，仍出原子，不静默丢单元）。"""
        name_node = getattr(node, name_field, None) if name_field else None
        if isinstance(name_node, Node) and name_node.content:
            return str(name_node.content)
        return ""
