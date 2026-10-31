"""单元图（块 5）：多入口 ⇒ 多根森林；边由发现/预处理阶段产，kind 是配置数据。

判据（`docs/gaps/gap-unit-graph.md`）：
- `check([...])` 返回 `graph`（roots / nodes / edges）；多入口 ⇒ 多个 root；
- C：`include` 边（kind = 语言包声明的指令关键字）；
- V：实例化边（kind = 语言包 `[structure] module_inst_rule`）；
- 反查 `inverse(file)` = 能到达该文件的 roots（共享文件返回多个 root）；
- CLI `tpc check a b --json` 同口径（多参数）。

Doc: analyzer/unit_graph.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer.checker import ProjectChecker
from analyzer.unit_graph import UnitGraph, norm_node

_REF = _ROOT / "tests" / "e2e" / "samples" / "real" / "ref"


def _graph(entries, rules_dir, include_dirs=None) -> dict:
    checker = ProjectChecker(rules_dir=rules_dir, include_dirs=include_dirs)
    return checker.check(entries)["graph"]


def test_c_include_edges_multi_root(tmp_path):
    """C：两个入口都被同一头文件包含 ⇒ 两条 include 边、两个 root、反查 2。"""
    (tmp_path / "a.h").write_text("int f(void);\n", encoding="utf-8")
    (tmp_path / "main.c").write_text(
        '#include "a.h"\nint main(void){return 0;}\n', encoding="utf-8"
    )
    (tmp_path / "other.c").write_text(
        '#include "a.h"\nint other(void){return 0;}\n', encoding="utf-8"
    )
    main_c, other_c = str(tmp_path / "main.c"), str(tmp_path / "other.c")
    graph = _graph([main_c, other_c], "grammar/c", include_dirs=[str(tmp_path)])

    assert len(graph["roots"]) == 2, graph
    kinds = {e["kind"] for e in graph["edges"]}
    assert kinds == {"include"}, f"边 kind 应来自指令关键字（配置数据）：{kinds}"
    target = norm_node(str(tmp_path / "a.h"))
    assert target in {e["target"] for e in graph["edges"]}

    ug = UnitGraph(
        graph["roots"],
        [(e["kind"], e["source"], e["target"]) for e in graph["edges"]],
    )
    assert len(ug.inverse(str(tmp_path / "a.h"))) == 2, ug.inverse(str(tmp_path / "a.h"))
    assert ug.dependencies(main_c) == [target]
    assert target in ug.reachable(main_c)


def test_verilog_instantiation_edges_single_root():
    """V：实例化边 kind = 语言包 `module_inst_rule`（不是引擎字面量）。"""
    entry = str(_REF / "ref_uart.v")
    graph = _graph([entry], "grammar/verilog")

    assert graph["roots"] == [norm_node(entry)]
    kinds = {e["kind"] for e in graph["edges"]}
    assert kinds == {"ModuleInst"}, kinds
    targets = {os.path.basename(e["target"]) for e in graph["edges"]}
    assert {"ref_uart_rx.v", "ref_uart_tx.v"} <= targets


def test_graph_nodes_cover_roots_and_targets():
    """节点集 = roots ∪ 边端点；自环/重复边被去掉（图是规范化的）。"""
    entry = str(_REF / "ref_uart.v")
    graph = _graph([entry, entry], "grammar/verilog")  # 重复入口去重
    assert len(graph["roots"]) == 1
    endpoints = {e["source"] for e in graph["edges"]} | {e["target"] for e in graph["edges"]}
    assert set(graph["nodes"]) == {*graph["roots"], *endpoints}
    assert len({(e["kind"], e["source"], e["target"]) for e in graph["edges"]}) == len(
        graph["edges"]
    )


def test_cli_check_accepts_multiple_entries():
    """CLI：`tpc check a b --json` 接受多参数，图里 roots=2。"""
    entries = [str(_REF / "ref_uart.v"), str(_REF / "ref_uart_rx.v")]
    proc = subprocess.run(
        [sys.executable, "main.py", "check", *entries, "--json"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    data = json.loads(proc.stdout)
    assert len(data["graph"]["roots"]) == 2, data["graph"]["roots"]
    assert data["graph"]["edges"], "CLI 多入口的图至少应有实例化边"


class _FakeSession:
    """精化供源的最小会话替身（memo / module_index / 渲染 / 声明面）。"""

    def __init__(self, memo: dict) -> None:
        self.memo = memo
        self.module_index: dict = {}

    def rule(self, key: str) -> str:
        return ""

    def field(self, key: str) -> str:
        return ""

    def render_subtree(self, node) -> str:
        return ""


def test_elaboration_consumes_graph(tmp_path):
    """块 6：精化原子/服务面消费图——图外文件不得进入文件原子/服务视图。"""
    from types import SimpleNamespace

    from analyzer.elaboration import SCOPE_FILE, ElaborationService, StructureAtomSource
    from analyzer.unit_graph import UnitGraph

    a = str(tmp_path / "a.v")
    b = str(tmp_path / "b.v")
    (tmp_path / "a.v").write_text("module a; endmodule\n", encoding="utf-8")
    (tmp_path / "b.v").write_text("module b; endmodule\n", encoding="utf-8")
    memo = {a: SimpleNamespace(ast=None, inst_sites=[]),
            b: SimpleNamespace(ast=None, inst_sites=[])}
    session = _FakeSession(memo)
    graph = UnitGraph([a], [], {})  # 图只含 a（b 是"已发现但不在图里"的文件）

    atoms = StructureAtomSource(session, graph).atoms(SCOPE_FILE)
    assert [os.path.basename(atom.key) for atom in atoms] == ["a.v"], atoms
    assert [os.path.basename(p) for p, _ in ElaborationService(session, graph).files()] == ["a.v"]

    # 不传图 = 旧行为（直读会话），证明差异来自"消费图"
    atoms_plain = StructureAtomSource(session).atoms(SCOPE_FILE)
    assert {os.path.basename(atom.key) for atom in atoms_plain} == {"a.v", "b.v"}
