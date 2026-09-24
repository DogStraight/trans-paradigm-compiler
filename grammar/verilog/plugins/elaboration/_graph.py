"""_graph.py — 层 3 信号驱动/负载图（精化项 `signal_graph`）。

引擎侧（`analyzer/elaboration/`）只按项列表驱动；**Verilog 的驱动/负载语义**在本文件。
逐字搬迁自 `analyzer/structure.py::SignalGraphBuilder`（400 行 / 22 方法），算法不动
（对拍见 `tests/engine/analyzer/test_elaboration_signal_graph.py`）。

## 与引擎版的差异：**只换数据来源，不改算法**

| 数据 | 引擎版来源 | 本文件来源 |
|---|---|---|
| 实例连接 | `FileResult.connections` | 本插件产物 `connections`（`depends_on`） |
| 端口方向 | `ModuleInfo.ports` | 本插件产物 `port_decls` |
| generate 活性 | 引擎 `gen_activity` 角色产物 | 本插件产物 `gen_activity` |
| 文件 / 单元 | 摸 `ctx.memo` / `ctx.module_index` | **服务面** `files()` / `unit_node()` / `unit_file()` |
| 声明值 | `[structure]` / `[structure.fields]` | 本文件末的常量（语言知识在插件） |

三个产物都经 `ctx.products` 直读（`depends_on` 保证先跑），**不经引擎中转**。

## 图形状（保持不变，消费方迁移才是机械的）

    (单元名, 信号名) → {"drivers": [驱动源标识], "loads": [负载源标识]}

驱动源标识带文件/实例路径前缀（`file:assign#N` / `file:always#N` / `top/u_a/u_b`），
消费方按"源所在文件"归属，避免跨文件重复报。
"""
from __future__ import annotations

import os
import re

from core.define import Node, iter_nodes
from core.errors import ConfigError

from analyzer.elaboration.driver import Atom, SolveCtx

# ── 本语言包的驱动/负载形态（原 `[structure]` / `[structure.fields]` 声明） ──
_ASSIGN_RULE = "AssignStmt"
_PROC_ASSIGN_RULES = ("BlockingAssign", "NonBlockingAssign")
_PROC_BLOCK_RULES = ("AlwaysStmt", "InitialStmt")
_ASSIGN_TARGET = "target"
_ASSIGN_EXTRAS = "extras"
_ASSIGN_EXTRA_TARGET = "target"
_OUT_DIRS = frozenset({"output"})
_INOUT_DIRS = frozenset({"inout"})
_UNIT_DECL_RULE = "ModuleDecl"
_UNIT_NAME_FIELD = "module_name"

# 简单信号名（标识符形态）——常量/拼接/位选/层次引用都不算驱动目标
_SIGNAL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 产物键（本文件与 `_elaborator.py` 共用同一串名）
_CFG_CONNECTIONS = "connections"
_CFG_PORT_DECLS = "port_decls"
_CFG_GEN_ACTIVITY = "gen_activity"
_PROVIDES_SIGNAL_GRAPH = "signal_graph"


def solve_signal_graph(hits: list[Node], atom: Atom, ctx: SolveCtx) -> dict | None:
    """全工程信号驱动/负载图（`project` 作用域 → 单原子，产物键 = ""）。"""
    del hits, atom  # 项目级项：不定位、不按原子归位
    return {_PROVIDES_SIGNAL_GRAPH: _GraphRunner(ctx).build()}


# ── 图条目小助手（原引擎 `_graph_entry` / `_append_ref`，仅层 3 用） ──

def _graph_entry(graph: dict, key: tuple) -> dict:
    """取（或建）信号图条目 `{"drivers": [], "loads": []}`。"""
    if key not in graph:
        graph[key] = {"drivers": [], "loads": []}
    return graph[key]


def _append_ref(entry: dict, kind: str, ref: str) -> None:
    """把源标识记入条目的 `kind` 列表（已存在则不重复）。"""
    if ref not in entry[kind]:
        entry[kind].append(ref)


def _is_signal_expr(text: str) -> bool:
    """简单信号名（标识符形态）→ True；常量/拼接/位选/层次引用 → False。"""
    return bool(_SIGNAL_RE.match(text.strip()))


class _GraphRunner:
    """层 3 构建器：一次运行一个实例（持有 per-run 缓存）。"""

    def __init__(self, ctx: SolveCtx) -> None:
        service = ctx.service
        if service is None:
            raise ConfigError(
                "[elaborator] 项 'signal_graph' 需要文件/渲染服务（ctx.service），"
                "调用方未提供"
            )
        self._svc = service
        self._connections = ctx.products.get(_CFG_CONNECTIONS) or {}
        self._ports = ctx.products.get(_CFG_PORT_DECLS) or {}
        self._gen = ctx.products.get(_CFG_GEN_ACTIVITY) or {}
        self._files: dict[str, Node | None] | None = None
        self._module_map: dict[str, dict[int, str]] = {}
        self._src_cache: dict[tuple, tuple] = {}
        self._insts: dict[str, list] | None = None

    # ── 服务面小助手 ──

    def _render(self, node) -> str:
        return self._svc.render(node) if isinstance(node, Node) else ""

    def _file_asts(self) -> dict[str, Node | None]:
        if self._files is None:
            self._files = {path: ast for path, ast in self._svc.files()}
        return self._files

    def _ast_of(self, path: str) -> Node | None:
        return self._file_asts().get(path)

    def _in_active_generate(self, path: str, node) -> bool:
        """节点是否在**选中**的 generate 互斥分支内（产物缺失 → 全活跃，保守）。"""
        if node is None:
            return True
        table = self._gen.get(path)
        if not table:
            return True
        return table.get(id(node), True)

    def _module_of(self, path: str, node) -> str:
        """节点所属单元名（per-file 预计算 `{id(节点): 单元名}`，查询 O(1)）。"""
        if node is None:
            return ""
        table = self._module_map.get(path)
        if table is None:
            table = self._precompute_module_map(self._ast_of(path))
            self._module_map[path] = table
        return table.get(id(node), "")

    def _precompute_module_map(self, ast: Node | None) -> dict[int, str]:
        """一次 DFS：栈元素 = (节点, 当前单元名)；单元声明进入时更新，子树继承。

        嵌套单元罕见（SV 特性），内层覆盖外层名——与引擎同语义。
        """
        mapping: dict[int, str] = {}
        if ast is None:
            return mapping
        stack: list[tuple[Node, str]] = [(ast, "")]
        while stack:
            node, unit = stack.pop()
            if node.node_name == _UNIT_DECL_RULE:
                nm = getattr(node, _UNIT_NAME_FIELD, None)
                unit = nm.content if isinstance(nm, Node) else ""
            mapping[id(node)] = unit
            for child in node.iter_children():
                stack.append((child, unit))
        return mapping

    def _port_direction(self, unit: str, port_name: str) -> str:
        """端口方向（单元未定义 / 无该端口 → ""）。"""
        ports = self._ports.get(unit)
        if not ports:
            return ""
        rec = ports.get(port_name)
        return str(rec.get("direction", "")) if rec else ""

    def _assign_targets(self, node: Node):
        """赋值语句的驱动目标节点（主目标 + 多目标后缀）。"""
        tgt = getattr(node, _ASSIGN_TARGET, None)
        if isinstance(tgt, Node):
            yield tgt
        for ex in getattr(node, _ASSIGN_EXTRAS, None) or []:
            if not isinstance(ex, Node):
                continue
            et = getattr(ex, _ASSIGN_EXTRA_TARGET, None)
            if isinstance(et, Node):
                yield et

    def _module_insts(self) -> dict[str, list]:
        """{单元名: [(实例名, 被实例化单元名, 连接)]}——per-unit 实例表（穿透用）。"""
        if self._insts is not None:
            return self._insts
        out: dict[str, list] = {}
        for path, conns in self._connections.items():
            for conn in conns:
                mod_name = self._module_of(path, conn["inst_node"])
                if not mod_name:
                    continue
                out.setdefault(mod_name, []).append(
                    (conn["inst_name"], conn["module_name"], conn)
                )
        self._insts = out
        return out

    # ── 顶层装配 ──

    def build(self) -> dict:
        """汇总所有文件的三类贡献 → `{(单元, 信号): {drivers, loads}}`。"""
        graph: dict[tuple, dict] = {}
        for path, ast in self._svc.files():
            self._sg_assign_drivers(path, ast, graph)
            self._sg_proc_drivers(path, ast, graph)
            self._sg_connections(path, graph)
        return graph

    def _add_driver(self, graph: dict, unit: str, sig: str, ref: str) -> None:
        """登记驱动源（(单元, 信号) 键控，源标识去重）。"""
        _append_ref(_graph_entry(graph, (unit, sig)), "drivers", ref)

    def _add_load(self, graph: dict, unit: str, sig: str, ref: str) -> None:
        """登记负载源（(单元, 信号) 键控，源标识去重）。"""
        _append_ref(_graph_entry(graph, (unit, sig)), "loads", ref)

    # ── 三类贡献之一：连续赋值 ──

    def _sg_assign_drivers(self, path: str, ast: Node | None, graph: dict) -> None:
        """连续赋值驱动（单元级 assign 并发驱动；多目标 `extras` 展开）。"""
        if ast is None:
            return
        assign_idx = 0
        for node in iter_nodes(ast):
            if node.node_name != _ASSIGN_RULE:
                continue
            assign_idx += 1
            mod_name = self._module_of(path, node)
            if not self._in_active_generate(path, node):
                continue  # 所在 generate 互斥分支未选中
            inst_ref = f"{os.path.basename(path)}:assign#{assign_idx}"
            for tgt in self._assign_targets(node):
                sig = self._render(tgt)
                if not sig or not _is_signal_expr(sig):
                    continue
                self._add_driver(graph, mod_name, sig, inst_ref)

    # ── 三类贡献之二：过程赋值 ──

    def _sg_proc_drivers(self, path: str, ast: Node | None, graph: dict) -> None:
        """过程赋值驱动（always/initial 内的阻塞/非阻塞赋值目标）。

        驱动源 = **过程块**（同一 always 内多赋值算一个驱动者；不同块或
        always+assign 才冲突）——对标 Verilator MULTIDRIVEN。
        """
        if ast is None:
            return
        assign_block = self._proc_assign_blocks(ast)
        block_sigs = self._proc_block_signals(path, ast, assign_block)
        block_idx = 0
        for blk_node, sigs in block_sigs.values():
            block_idx += 1
            mod_name = self._module_of(path, blk_node)
            inst_ref = f"{os.path.basename(path)}:always#{block_idx}"
            for sig in sigs:
                self._add_driver(graph, mod_name, sig, inst_ref)

    def _proc_assign_blocks(self, ast: Node) -> dict[int, Node | None]:
        """赋值节点 → 所属过程块节点（blk 可为 None：不在任何过程块内）。"""
        assign_block: dict[int, Node | None] = {}
        todo: list[tuple[Node | None, Node | None]] = [(ast, None)]
        while todo:
            node, blk = todo.pop()
            if node is None:
                continue
            if node.node_name in _PROC_BLOCK_RULES:
                blk = node
            if node.node_name in _PROC_ASSIGN_RULES:
                assign_block[id(node)] = blk
            for child in node.iter_children():
                todo.append((child, blk))
        return assign_block

    def _proc_block_signals(
        self, path: str, ast: Node, assign_block: dict
    ) -> dict[int, tuple]:
        """过程块 → 该块内被赋值的信号集合（块内多赋值去重为同一驱动源）。

        未选中 generate 分支内的赋值不计。
        """
        block_sigs: dict[int, tuple] = {}
        for node in iter_nodes(ast):
            if node.node_name not in _PROC_ASSIGN_RULES:
                continue
            blk = assign_block.get(id(node))
            if blk is None or not self._in_active_generate(path, node):
                continue
            tgt = getattr(node, _ASSIGN_TARGET, None)
            sig = self._render(tgt)
            if not sig or not _is_signal_expr(sig):
                continue
            if id(blk) not in block_sigs:
                block_sigs[id(blk)] = (blk, set())
            block_sigs[id(blk)][1].add(sig)
        return block_sigs

    # ── 三类贡献之三：实例化连接 ──

    def _sg_connections(self, path: str, graph: dict) -> None:
        """实例化点连接：命名连接按端口方向记驱动/负载；位置连接保守记负载。"""
        for conn in self._connections.get(path) or []:
            mod_name = self._module_of(path, conn["inst_node"])
            if not self._in_active_generate(path, conn["inst_node"]):
                continue  # 实例化点所在 generate 分支未选中
            inst_ref = f"{os.path.basename(conn['file'])}:{conn['inst_name']}"
            self._sg_named_connection(graph, conn, mod_name, inst_ref)
            self._sg_positional_connection(graph, conn, mod_name, inst_ref)

    def _sg_inout_connection(
        self, graph: dict, unit: str, sig: str, ref: str
    ) -> None:
        """inout 端口：既作驱动又作负载。"""
        self._add_driver(graph, unit, sig, ref)
        self._add_load(graph, unit, sig, ref)

    def _sg_named_connection(
        self, graph: dict, conn: dict, mod_name: str, inst_ref: str
    ) -> None:
        """命名连接：按端口方向记驱动/负载；output 走层 3 穿透。"""
        for port_name, sig in conn["connects"].items():
            if not sig or not _is_signal_expr(sig):
                continue
            direction = self._port_direction(conn["module_name"], port_name)
            if direction in _OUT_DIRS:
                # 驱动源穿透到模块内部真实源（带实例路径）：穿透成功 → 用穿透源；
                # 悬空 output（定义但无驱动）→ 不记（对齐 Verilator elaboration）；
                # 黑盒（未定义）→ 原子源兜底（保守）。
                self._sg_emit_penetrated(
                    _graph_entry(graph, (mod_name, sig)), conn, port_name, inst_ref
                )
            elif direction in _INOUT_DIRS:
                self._sg_inout_connection(graph, mod_name, sig, inst_ref)
            else:  # input / 未知 → 负载
                self._add_load(graph, mod_name, sig, inst_ref)

    def _sg_emit_penetrated(
        self, entry: dict, conn: dict, port_name: str, inst_ref: str
    ) -> None:
        """output 端口驱动源：穿透结果 / 黑盒原子源兜底 / 悬空不记。"""
        pen, pen_defined = self._resolve_port_drivers(
            conn["module_name"], port_name, inst_ref, set()
        )
        if pen:
            for s in pen:
                if s not in entry["drivers"]:
                    entry["drivers"].append(s)
        elif not pen_defined and inst_ref not in entry["drivers"]:
            entry["drivers"].append(inst_ref)

    def _sg_positional_connection(
        self, graph: dict, conn: dict, mod_name: str, inst_ref: str
    ) -> None:
        """位置连接：方向靠单元端口表按序匹配；未知方向保守记负载。"""
        for sig in conn["ordered"]:
            if not sig or not _is_signal_expr(sig):
                continue
            self._add_load(graph, mod_name, sig, inst_ref)

    # ── 驱动穿透（output 端口 → 模块内部真实源，带实例链路径） ──

    def _port_driver_sources(
        self, module: str, port: str, seen: set
    ) -> tuple[list | None, bool]:
        """单元内端口驱动源（裸源，无路径）→ (sources, 单元是否定义)。

        遍历**目标单元子树**而非文件全树——同文件多单元同名 assign 不能污染。
        `(None, False)` = 未定义（黑盒，调用方兜底原子源）；`([], True)` = 定义但端口悬空。
        """
        cache_key = (module, port)
        if cache_key in self._src_cache:
            return self._src_cache[cache_key]
        if module in seen:
            return [], True
        seen = seen | {module}
        mnode = self._svc.unit_node(module)
        path = self._svc.unit_file(module)
        if mnode is None or not path or self._ast_of(path) is None:
            return None, False
        sources = (
            self._port_src_from_assigns(path, mnode, port)
            + self._port_src_from_insts(module, port)
            + self._port_src_from_procs(path, mnode, port)
        )
        result = (list(dict.fromkeys(sources)), True)
        self._src_cache[cache_key] = result
        return result

    def _port_src_from_assigns(self, path: str, mnode: Node, port: str) -> list[str]:
        """端口裸源①：单元内连续赋值目标 == 端口（限定单元子树）。"""
        out: list[str] = []
        idx = 0
        for node in iter_nodes(mnode):
            if node.node_name != _ASSIGN_RULE:
                continue
            idx += 1
            if not self._in_active_generate(path, node):
                continue
            for tgt in self._assign_targets(node):
                if self._render(tgt) == port:
                    out.append(f"assign#{idx}")
        return out

    def _port_src_from_insts(self, module: str, port: str) -> list[str]:
        """端口裸源②：单元内更深实例 output/inout 连接 == 端口 → 子引用。"""
        out: list[str] = []
        for inst_name, inst_mod, conn in self._module_insts().get(module, []):
            if conn is None:
                continue
            for pname, sig in conn["connects"].items():
                if sig != port:
                    continue
                dirn = self._port_direction(inst_mod, pname)
                if dirn in _OUT_DIRS or dirn in _INOUT_DIRS:
                    out.append(f"inst:{inst_name}:{pname}")
        return out

    def _port_src_from_procs(self, path: str, mnode: Node, port: str) -> list[str]:
        """端口裸源③：单元内过程赋值目标 == 端口（always 驱动 output 端口）。"""
        out: list[str] = []
        for node in iter_nodes(mnode):
            if node.node_name not in _PROC_ASSIGN_RULES:
                continue
            if not self._in_active_generate(path, node):
                continue
            if self._render(getattr(node, _ASSIGN_TARGET, None)) == port:
                out.append("proc")
        return out

    def _inst_module_name_of(self, module: str, iname: str) -> str:
        """实例名 → 被实例化单元名（per-unit 实例表查找；未知 → ""）。"""
        for i_name, i_mod, _ in self._module_insts().get(module, []):
            if i_name == iname:
                return i_mod
        return ""

    def _resolve_inst_source(
        self, module: str, src: str, path: str, seen: set
    ) -> list[str]:
        """`inst:` 子引用 → 完整路径标识（递归穿透）。

        子单元黑盒（未定义）→ 保守记实例路径；悬空（定义但无驱动）→ 不记。
        """
        _, iname, iport = src.split(":", 2)
        inst_mod = self._inst_module_name_of(module, iname)
        if not inst_mod:
            return []
        sub, sub_defined = self._resolve_port_drivers(
            inst_mod, iport, f"{path}/{iname}", seen
        )
        if sub:
            return sub
        if not sub_defined:
            return [f"{path}/{iname}"]  # 黑盒保守
        return []

    def _resolve_port_drivers(
        self, module: str, port: str, path: str, seen: set
    ) -> tuple[list, bool]:
        """端口驱动源 → (完整路径标识列表, 单元是否定义)（层 3 穿透）。"""
        sources, defined = self._port_driver_sources(module, port, seen)
        if sources is None:
            return [], defined
        out: list[str] = []
        for src in sources:
            if src.startswith("inst:"):
                out.extend(self._resolve_inst_source(module, src, path, seen))
            else:
                out.append(f"{path}:{src}")
        return out, defined
