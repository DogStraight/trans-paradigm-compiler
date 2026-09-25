"""driver.py — 精化驱动器：按项列表驱动「定位 → 求解 → 归位 → 核验」。

引擎侧**唯一执行体，语言无关**：它不认识任何 Verilog 语义——只知道"在原子子树里
按声明找节点（或把原子根交给求解器）、调插件给的求解函数、把结果按声明的容器键归位"。
这是 ADR-0019 的"引擎最小可视单位 = 文件"在代码上的落点。

分工：
- **引擎**：原子枚举（文件 / 单元 / 工程）、声明式定位、拓扑序、容器与生命周期、
  强方向核验（求解器返回未声明的键 → fail）。
- **插件**：项列表（数据）+ 全部语义求解与定位（代码）。

未声明能力（`spec=None`）→ 不执行任何项、不写容器 = **降级**（调用方按"无精化"
处理，退回单文件 lint + analyze）。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from core._protocol import CTX_ELABORATION
from core.define import Node, collect_nodes
from core.errors import ConfigError

from analyzer.elaboration.contract import ElaborationItem, ElaboratorSpec
from analyzer.elaboration.service import ServiceApi


@dataclass(frozen=True)
class Atom:
    """执行原子：一个文件 / 一个单元 / 整个工程（引擎只认这三类）。

    `node` = 定位起点（单元节点 / 文件根；工程级可为 None）。
    """

    key: str
    path: str = ""
    node: Node | None = None


class AtomSource(Protocol):
    """原子来源（引擎侧文件层供源，实现见 `analyzer/elaboration/atoms.py`）。"""

    def atoms(self, scope: str) -> Iterable[Atom]:
        """按 `scope` 枚举原子（`file` / `unit` / `project`）。"""
        ...


@dataclass
class SolveCtx:
    """求解上下文：**已产出**的容器（读取用）+ 语言无关服务句柄。

    `products` 是引擎侧容器的活视图：后声明的项按 `depends_on` 读先声明项的产物
    （跨文件传播就靠这条通道）。
    """

    products: Mapping[str, Mapping[str, Any]]
    service: ServiceApi | None = None


@dataclass
class ElaborationResult:
    """一次精化的结果：容器（容器键 → 原子键 → 值）+ 实际执行序。"""

    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    ran: tuple[str, ...] = ()


class Elaborator:
    """精化驱动器（未声明能力 → 全空降级，零副作用）。"""

    def __init__(self, spec: ElaboratorSpec | None) -> None:
        self._spec = spec

    @property
    def declared(self) -> bool:
        """该语言包是否声明了精化能力。"""
        return self._spec is not None

    def container(self) -> dict[str, dict[str, Any]]:
        """空容器：为每个声明的容器键**预置空表**。

        预置是刻意的——"某原子无此类值"是常态（无参数的模块本就没有
        `param_default`），若键时有时无常，下游就得两套写法。
        """
        if self._spec is None:
            return {}
        return {key: {} for it in self._spec.items for key in it.provides}

    def run(
        self,
        source: AtomSource,
        extra: dict,
        service: ServiceApi | None = None,
    ) -> ElaborationResult:
        """执行全部精化项；声明了能力时把容器写进 `extra[CTX_ELABORATION]`。"""
        if self._spec is None:
            return ElaborationResult()
        products = self.container()
        ran: list[str] = []
        for item in self._spec.order():
            self._run_item(item, source, products, service)
            ran.append(item.name)
        extra[CTX_ELABORATION] = products
        return ElaborationResult(products=products, ran=tuple(ran))

    # ── 单项执行 ──

    def _run_item(
        self,
        item: ElaborationItem,
        source: AtomSource,
        products: dict[str, dict[str, Any]],
        service: ServiceApi | None,
    ) -> None:
        solver = self._solver(item.solver)
        for atom in source.atoms(item.scope):
            ctx = SolveCtx(products=products, service=service)
            hits = self._locate(item, atom, ctx)
            out = solver(hits, atom, ctx)
            if out is None:
                continue  # 本原子无此类值（合法）
            self._accept(item, atom, out, products)

    def _solver(self, name: str):
        """取求解/定位函数（解析期已 fail-fast，此处仅收窄类型）。"""
        assert self._spec is not None
        return self._spec.solvers[name]

    def _locate(
        self, item: ElaborationItem, atom: Atom, ctx: SolveCtx
    ) -> list[Node]:
        """定位。三种形态：

        - 声明式 `locator`：原子子树内按规则名收节点（先根序）；
        - `locator_fn`：交插件做原子级定位算法；
        - **都没声明**：把原子根交给求解器（`hits = [atom.node]`）——"怎么找"本身
          是语言知识，由插件自己走子树（P2 实测：`param_default` 的值分散在两种
          节点形态，单条规则名表达不了）。
        """
        if item.locator is not None:
            if atom.node is None:
                return []
            return collect_nodes(atom.node, item.locator.rule)
        if item.locator_fn is not None:
            locator = self._solver(item.locator_fn)
            return list(locator(atom, ctx) or [])
        return [] if atom.node is None else [atom.node]

    @staticmethod
    def _accept(
        item: ElaborationItem,
        atom: Atom,
        out: Mapping[str, Any],
        products: dict[str, dict[str, Any]],
    ) -> None:
        """归位 + 强方向核验：求解器**不得返回未声明的容器键**。"""
        if not isinstance(out, Mapping):
            raise ConfigError(
                f"[elaborator] 项 '{item.name}' 求解器须返回表或 None，"
                f"得到 {type(out).__name__}"
            )
        undeclared = sorted(set(out) - set(item.provides))
        if undeclared:
            raise ConfigError(
                f"[elaborator] 项 '{item.name}' 产出未声明的容器键: "
                f"{', '.join(undeclared)}（声明: {', '.join(item.provides)}）"
            )
        for key, value in out.items():
            # **原子键冲突取先**（与引擎单元索引"首个定义者优先"同口径）：
            # 同名单元在多个文件重复定义时，`module_index` 保留**先发现**的定义；
            # 产物若"后写覆盖"，引擎按单元名取产物就会取到**另一个文件**的值
            # （端口表/参数表错配 → 跨文件检查静默错判）。故此处 setdefault 而非赋值。
            products[key].setdefault(atom.key, value)
