"""单元图（块 5）：多入口 ⇒ 多根森林；边由发现/预处理阶段产，kind 是配置数据。

判据（`docs/gaps/gap-unit-graph.md`）：
- `check([...])` 返回 `graph`（roots / nodes / edges）；多入口 ⇒ 多个 root；
- C：`include` 边（kind = 注册能力名 `include`）；
- V：实例化边（kind = 注册能力名 `instantiation`，语言包 `[[unit_graph.edges]]` 声明）；
- 反查 `inverse(file)` = 能到达该文件的 roots（共享文件返回多个 root）；
- CLI `tpc check a b --json` 同口径（多参数）。

Doc: analyzer/unit_graph.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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
    assert kinds == {"include"}, f"边 kind 应来自语言包声明（配置数据）：{kinds}"
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
    """V：实例化边 kind = 注册能力名 `instantiation`（不是规则名字面量）。"""
    entry = str(_REF / "ref_uart.v")
    graph = _graph([entry], "grammar/verilog")

    assert graph["roots"] == [norm_node(entry)]
    kinds = {e["kind"] for e in graph["edges"]}
    assert kinds == {"instantiation"}, kinds
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


def test_render_tree_single_and_multi_root():
    """文本树出口：单根/多根、单元定义后缀、kind 标注。"""
    a, b, c = map(norm_node, (str(_ROOT / "a.v"), str(_ROOT / "b.v"), str(_ROOT / "c.v")))
    g = UnitGraph([a], [("instantiation", a, b), ("instantiation", a, c)],
                  {"a": a, "b": b, "c": c})
    assert g.render_tree().splitlines() == [
        f"● a.v  (a)  [root]",
        f"├─ [instantiation] b.v  (b)",
        f"└─ [instantiation] c.v  (c)",
    ]

    forest = UnitGraph([a, b], [("instantiation", a, c)], {"a": a, "b": b, "c": c})
    assert forest.render_tree().splitlines() == [
        f"● a.v  (a)  [root]",
        f"└─ [instantiation] c.v  (c)",
        f"● b.v  (b)  [root]",
    ]


def test_render_tree_marks_seen_on_diamond():
    """共享节点第二次出现标 (seen) 且不再展开（防重复展开/环）。"""
    a, b, c, d = map(
        norm_node, (str(_ROOT / f"{n}.v") for n in "abcd")
    )
    g = UnitGraph(
        [a],
        [("K", a, b), ("K", a, c), ("K", b, d), ("K", c, d)],
        {"a": a, "b": b, "c": c, "d": d},
    )
    lines = g.render_tree().splitlines()
    assert any(line.endswith("[K] b.v  (b)") for line in lines)
    assert sum(1 for ln in lines if ln.endswith("[K] d.v  (d)")) == 1
    assert sum(1 for ln in lines if ln.endswith("[K] d.v  (d)  (seen)")) == 1


class _EdgeCtx:
    """build_unit_graph 的最小会话替身（只提供边来源与定义索引）。"""

    memo: dict = {}
    module_index: dict = {}
    unit_edges: list = []


def _build_with(monkeypatch, edges, legacy=None):
    from analyzer import unit_graph as ug

    monkeypatch.setattr(ug, "_unit_graph_edges", edges)
    monkeypatch.setattr(ug, "_legacy_edge_kinds", legacy)
    return ug.build_unit_graph(_EdgeCtx(), [])


def test_unknown_edge_channel_fails_fast(monkeypatch):
    """`from` 不在通道表 → ConfigError，且报错列出已注册通道。"""
    from core.errors import ConfigError

    with pytest.raises(ConfigError, match="已注册通道"):
        _build_with(monkeypatch, [{"kind": "custom_link", "from": "structure.nope"}])


def test_duplicate_edge_kind_fails_fast(monkeypatch):
    """同一 kind 声明两次（包自己写错）→ ConfigError。"""
    from core.errors import ConfigError

    with pytest.raises(ConfigError, match="kind 重复"):
        _build_with(
            monkeypatch,
            [
                {"kind": "include", "from": "preprocessor.include_edges"},
                {"kind": "include", "from": "structure.unit_edges"},
            ],
        )


def test_legacy_edge_kinds_key_fails_fast_with_pointer(monkeypatch):
    """旧键 edge_kinds 不留兼容垫片：ConfigError 且消息指向新写法。"""
    from core.errors import ConfigError

    with pytest.raises(ConfigError, match=r"\[\[unit_graph\.edges\]\]"):
        _build_with(monkeypatch, [], legacy=["include"])


def test_invalid_edge_kind_name_fails_fast(monkeypatch):
    """kind 必须是小写标识符（`^[a-z][a-z0-9_]*$`）。"""
    from core.errors import ConfigError

    with pytest.raises(ConfigError, match="kind 须匹配"):
        _build_with(monkeypatch, [{"kind": "Custom-Link", "from": "structure.unit_edges"}])


def test_cli_tree_flag():
    """CLI `--tree` 输出文本树（不打印诊断）。"""
    entry = str(_REF / "ref_uart.v")
    proc = subprocess.run(
        [sys.executable, "main.py", "check", entry, "--tree"],
        cwd=str(_ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "● ref_uart.v" in proc.stdout
    assert "├─ [instantiation] ref_uart_rx.v" in proc.stdout
    assert "No issues found" not in proc.stdout


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


def test_custom_edge_kind_from_pack_without_engine_change(tmp_path):
    """可扩展性硬证据：临时包声明 kind=custom_link + 已注册通道，不改引擎即出边。"""
    import shutil

    from core.config_registry import ConfigRegistry

    pack = tmp_path / "verilog_custom"
    shutil.copytree(
        _ROOT / "grammar" / "verilog",
        pack,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    tpc = pack / "tpc.toml"
    text = tpc.read_text(encoding="utf-8")
    anchor = 'kind = "include"\nfrom = "preprocessor.include_edges"'
    assert text.count(anchor) == 1
    text = text.replace(
        anchor,
        anchor
        + '\n\n[[unit_graph.edges]]\nkind = "custom_link"\nfrom = "structure.unit_edges"',
    )
    tpc.write_text(text, encoding="utf-8")
    try:
        graph = _graph(
            [str(_REF / "ref_uart.v")],
            str(pack),
            include_dirs=None,
        )
        kinds = {e["kind"] for e in graph["edges"]}
        assert "custom_link" in kinds, kinds
        assert "instantiation" in kinds, kinds
    finally:
        ConfigRegistry.load_language(
            "grammar/verilog", plugins_dir="grammar/verilog/plugins"
        )
