"""postpass 链：声明形态（表 + produces/requires）、链内契约、执行轨迹。

背景：链的执行顺序原先只由**组件名排序**碰巧成立；两条真实依赖只写在注释里
（typed_ports `_expand_ports` → `_check`、`hier_check` → `width_check` 服务）。
现声明为链内契约：顺序不满足即 fail-fast；每环执行进单元轨迹（链也是时点）。

Doc: analyzer/semantic_checks.md（postpass 声明与契约）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")

VERILOG_SRC = "module m;\n  wire a;\nendmodule\n"


def _load_verilog() -> None:
    from core.config_registry import ConfigRegistry
    from core.plugin_loader import load_all_components

    ConfigRegistry.load_all("grammar/verilog", plugins_dir="grammar/verilog/plugins")
    load_all_components("grammar/verilog/plugins")


def _write_postpass(tmp_path, body: str) -> str:
    """最小组件目录：一个 postpass 模块。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "_p.py").write_text(body, encoding="utf-8")
    return str(tmp_path)


def test_loaded_chain_declares_real_contracts() -> None:
    """两条真实依赖进入契约：顺序由声明保证（顺序错即 fail-fast）。"""
    from core.plugin_loader import get_analyzer_postpass_decls

    _load_verilog()
    names = [d["name"] for d in get_analyzer_postpass_decls()]
    contracts = {d["name"]: d for d in get_analyzer_postpass_decls()}

    expand = "_expand_ports.py:run_expand_ports"
    check = "_check.py:run_tp_check"
    assert contracts[expand]["produces"] == ["resolved_ports"]
    assert contracts[check]["requires"] == ["resolved_ports"]
    assert names.index(expand) < names.index(check)

    hier = "_hier_check.py:run_hier_check"
    width = "_width_check.py:run_width_check"
    assert contracts[hier]["produces"] == ["hier_member_table"]
    assert contracts[width]["requires"] == ["hier_member_table"]
    assert names.index(hier) < names.index(width)


def test_declaration_must_be_table(tmp_path) -> None:
    """字符串形态已撤销：postpass 声明须为表（迁移后无第二方言）。"""
    from core.plugin_loader import _load_postpasses

    with pytest.raises(ValueError, match="须为表"):
        _load_postpasses("/tmp", ["_p.py:run"])


def test_declaration_rejects_unknown_key(tmp_path) -> None:
    from core.plugin_loader import _load_postpasses

    cdir = _write_postpass(tmp_path / "c", "def run(analyzer, ctx):\n    return None\n")
    with pytest.raises(ValueError, match="未知键"):
        _load_postpasses(cdir, [{"run": "_p.py:run", "produced": []}])


def test_declaration_requires_run(tmp_path) -> None:
    from core.plugin_loader import _load_postpasses

    cdir = _write_postpass(tmp_path / "c", "def run(analyzer, ctx):\n    return None\n")
    with pytest.raises(ValueError, match="run 格式"):
        _load_postpasses(cdir, [{"produces": ["x"]}])


def test_declaration_loads_table_form(tmp_path) -> None:
    from core.plugin_loader import _load_postpasses

    cdir = _write_postpass(tmp_path / "c", "def run(analyzer, ctx):\n    return None\n")
    decls = _load_postpasses(cdir, [{"run": "_p.py:run", "produces": ["x"]}])
    assert [(d["name"], d["requires"], d["produces"]) for d in decls] == [
        ("_p.py:run", [], ["x"])
    ]
    assert callable(decls[0]["fn"])


def test_chain_contract_violation_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """链内 requires 无更早环节提供 → fail-fast（不静默跳过该环节）。"""
    import core.plugin_loader as pl
    from analyzer.context import AnalysisContext
    from analyzer.traversal import AnalysisTraversal

    monkeypatch.setattr(
        pl,
        "get_analyzer_postpass_decls",
        lambda: [
            {"name": "b.py:run", "fn": lambda a, c: None, "requires": ["x"], "produces": []}
        ],
    )
    analyzer = AnalysisTraversal({})
    analyzer._context = AnalysisContext()  # noqa: SLF001 — 单测直接驱动链
    analyzer._context.extra.pop("x", None)
    with pytest.raises(ValueError, match="requires 未满足"):
        analyzer._run_postpasses()


def test_chain_contract_satisfied_by_earlier_produces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """更早环节 produces 的名字可作为后续 requires 的满足源。"""
    import core.plugin_loader as pl
    from analyzer.context import AnalysisContext
    from analyzer.traversal import AnalysisTraversal

    seen: list[str] = []
    monkeypatch.setattr(
        pl,
        "get_analyzer_postpass_decls",
        lambda: [
            {"name": "a", "fn": lambda a, c: seen.append("a"), "requires": [], "produces": ["x"]},
            {"name": "b", "fn": lambda a, c: seen.append("b"), "requires": ["x"], "produces": []},
        ],
    )
    analyzer = AnalysisTraversal({})
    analyzer._context = AnalysisContext()
    analyzer._run_postpasses()
    assert seen == ["a", "b"]


def test_chain_recorded_in_unit_trace() -> None:
    """链执行进单元轨迹：哪一环跑了、报几条诊断（时点可见）。"""
    _load_verilog()
    r = run_pipeline_on_source(source=VERILOG_SRC, quiet=True, no_lint=True)
    entry = next(e for e in r["trace"] if e["kind"] == "analyze")
    records = entry["artifacts"]["postpasses"]
    names = [rec["name"] for rec in records]
    assert "_expand_ports.py:run_expand_ports" in names
    assert names[-1] == "check_rules"  # 链尾 = L1 声明式规则执行器
    assert all("diagnostics" in rec for rec in records)
