"""atoms.py — 引擎侧原子供源：文件 / 单元 / 工程（**零语言知识**）。

"单元"的判定走**声明**（`[structure]` 的单元规则名 + 单元名字段），引擎不认
"模块"；未声明单元规则 → 不产生单元原子（该语言包不做单元级精化）。

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

    def rule(self, key: str) -> str:
        """规则名类声明项（如单元声明规则）。"""
        ...

    def field(self, key: str) -> str:
        """节点字段名类声明项（如单元名字段）。"""
        ...


class StructureAtomSource:
    """按会话状态枚举原子（消费 `StructureCtx` 的会话状态与声明面）。"""

    def __init__(self, ctx: _SessionLike) -> None:
        self._ctx = ctx

    def atoms(self, scope: str) -> list[Atom]:
        if scope == SCOPE_PROJECT:
            return [Atom(key="", node=None)]
        out: list[Atom] = []
        for path, fr in self._ctx.memo.items():
            if scope == SCOPE_FILE:
                out.append(Atom(key=path, path=path, node=fr.ast))
            elif scope == SCOPE_UNIT:
                out.extend(self._units_of(path, fr.ast))
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
