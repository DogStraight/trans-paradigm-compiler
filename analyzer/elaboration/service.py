"""service.py — 引擎给插件的**语言无关服务句柄**（ADR-0019 决策 1 的③）。

引擎只做**文件操作**：读源 / 宏展开 / 解析 / AST 缓存 / 行映射 / 依赖发现编排。插件求解器
需要的一切通用能力（渲染子树、列出已发现文件、按单元名取节点与定义文件…）从此处取——
**按需开面**，不预先铺满。

已开的面：

| 面 | 用途（哪个项要它） |
|---|---|
| `render` | `param_default` / `port_decls` / `connections` / `gen_activity` 都要把 AST 子树取成文本 |
| `files` | 层 3 `signal_graph`：逐文件扫 assign/过程赋值/连接 |
| `unit_node` / `unit_file` | 层 3：驱动穿透要按**单元名**取单元子树与它所在的文件 |

⚠ 这些面**全部语言无关**（"有哪些文件""名字叫什么单元""节点在哪"与语言无关）；
语言语义仍只在插件里。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from core.define import Node


class ServiceApi(Protocol):
    """插件侧看到的服务面（引擎实现 = `ElaborationService`）。"""

    def render(self, node: Node) -> str:
        """AST 子树 → 文本。"""
        ...

    def files(self) -> Iterable[tuple[str, Node | None]]:
        """本次运行已发现的文件：`[(路径, AST 根 | None)]`（顺序 = 发现序）。"""
        ...

    def instantiation_sites(self, path: str) -> list[Node]:
        """文件里的实例化点节点（引擎发现期的产物；插件不再自行 `collect_nodes`）。"""
        ...

    def unit_node(self, unit_name: str) -> Node | None:
        """单元名 → 单元声明节点（未定义 → None）。"""
        ...

    def unit_file(self, unit_name: str) -> str:
        """单元名 → 定义文件路径（未定义 → ""）。"""
        ...


class _SessionLike(Protocol):
    """引擎会话里本服务需要的那几样（结构上满足 `StructureCtx`）。"""

    @property
    def memo(self) -> Mapping[str, Any]:
        """本次运行已发现的文件（路径 → FileResult）。"""
        ...

    @property
    def module_index(self) -> Mapping[str, Any]:
        """单元名 → 单元条目（有 `node` / `file`）。"""
        ...

    def render_subtree(self, node: Node) -> str:
        """引擎的渲染助手（语义见其实现）。"""
        ...


class ElaborationService:
    """服务句柄实现：把引擎既有的通用能力转交给插件。

    `render` 的语义**完全等同于** `StructureCtx.render_subtree`（strip；拿不到 → 空串，
    调用方按"不可判"保守处理）。此处只**转交**、不重新实现——故不引入新的异常处理点
    （渲染失败即空串是既有且已论证的设计，不是本次新增的吞异常）。

    **块 6（图化）**：传入 `UnitGraph` 时，`files()` 按**图节点**过滤、`instantiation_sites`
    直接取自引擎发现期产物（`FileResult.inst_sites`）——精化插件从此不自行 `collect_nodes`；
    未传图 = 旧行为（兼容/降级）。
    """

    def __init__(self, session: _SessionLike, graph: Any = None) -> None:
        self._session = session
        self._graph = graph
        self._nodes: set[str] | None = None
        if graph is not None:
            from analyzer.unit_graph import norm_node

            self._nodes = {norm_node(p) for p in graph.nodes}

    def render(self, node: Node) -> str:
        """AST 子树 → 文本（宽度表达式 / 参数默认值 / 连接信号等值文本）。"""
        return self._session.render_subtree(node)

    def files(self) -> list[tuple[str, Node | None]]:
        """本次运行已发现的文件（`memo` 顺序 = 发现序，层 3 依赖它保持确定性）。

        传了图时按**图节点**过滤（`memo` 可能含图外文件；顺序仍取 memo）。
        """
        if self._nodes is None:
            return [(path, fr.ast) for path, fr in self._session.memo.items()]
        from analyzer.unit_graph import norm_node

        return [
            (path, fr.ast)
            for path, fr in self._session.memo.items()
            if norm_node(path) in self._nodes
        ]

    def instantiation_sites(self, path: str) -> list[Node]:
        """文件里的实例化点节点（引擎发现期按语言包 `module_inst_rule` 收集的产物）。"""
        fr = self._session.memo.get(path)
        if fr is None:
            return []
        return list(getattr(fr, "inst_sites", []) or [])

    def unit_node(self, unit_name: str) -> Node | None:
        """单元名 → 单元声明节点（未定义 → None）。"""
        info = self._session.module_index.get(unit_name)
        return getattr(info, "node", None) if info is not None else None

    def unit_file(self, unit_name: str) -> str:
        """单元名 → 定义文件路径（未定义 → ""）。"""
        if self._graph is not None:
            hit = self._graph.definitions.get(unit_name)
            if hit:
                from analyzer.unit_graph import norm_node

                for path in self._session.memo:
                    if norm_node(path) == hit:
                        return path
                return hit
        info = self._session.module_index.get(unit_name)
        if info is None:
            return ""
        return str(getattr(info, "file", "") or "")
