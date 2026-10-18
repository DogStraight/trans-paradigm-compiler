"""postpass 的 `ast_optional` 键：解析失败文件的事实型检查（MAC 实参个数机制）。

背景（A2 ① 宏语义检查族）：实参不足时展开结果常是非法语法 ⇒ `ProjectChecker`
在 parse 失败时会跳过整个语义阶段。但宏调用点事实**先于解析**就有（展开期），
语义判定不需要 AST ⇒ 语言包可给自己的 postpass 声明 `ast_optional = true`：
`ProjectChecker` 在 `fr.ast is None` 时执行它们（`AnalysisTraversal.analyze_file_facts`），
`tpc check` 于是能在"展开坏掉语法"的文件上照常报宏实参诊断。

三条判据：
  1. 声明面：`ast_optional` 被接受、须为布尔；与 `requires = ["scope"]` 互斥（fail-fast）；
  2. 执行面：无 AST 模式**只跑** ast_optional 的 postpass（不做符号遍历、不跑 kind
     分发的声明式规则），诊断照常进 `context.diagnostics`；
  3. 不改变既有语义：未声明 ast_optional 的语言包（verilog）parse 失败仍跳过语义
     （由 `tests/engine/analyzer/test_checker.py::test_syntax_error_skips_semantic` 守）。

Doc: analyzer/semantic_checks.md（postpass 声明与契约） / core/plugin_loader.py
"""

from __future__ import annotations

import pytest

from analyzer.context import AnalysisContext
from analyzer.traversal import AnalysisTraversal


def _component(tmp_path, body: str) -> str:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "_p.py").write_text(body, encoding="utf-8")
    return str(tmp_path)


# ── 1. 声明面 ──────────────────────────────────────────────


def test_declaration_accepts_ast_optional(tmp_path) -> None:
    from core.plugin_loader import _load_postpasses

    cdir = _component(tmp_path, "def run(analyzer, ctx):\n    return None\n")
    decls = _load_postpasses(
        cdir, [{"run": "_p.py:run", "ast_optional": True}]
    )
    assert decls[0]["ast_optional"] is True
    # 缺省 = False（既有 postpass 行为不变）
    plain = _load_postpasses(cdir, [{"run": "_p.py:run"}])
    assert plain[0]["ast_optional"] is False


def test_declaration_rejects_non_bool_ast_optional(tmp_path) -> None:
    from core.plugin_loader import _load_postpasses

    cdir = _component(tmp_path, "def run(analyzer, ctx):\n    return None\n")
    with pytest.raises(ValueError, match="ast_optional 须为布尔值"):
        _load_postpasses(cdir, [{"run": "_p.py:run", "ast_optional": "yes"}])


def test_declaration_rejects_scope_requirement(tmp_path) -> None:
    """无 AST 就没有 scope ⇒ `ast_optional` + `requires=["scope"]` 契约矛盾。"""
    from core.plugin_loader import _load_postpasses

    cdir = _component(tmp_path, "def run(analyzer, ctx):\n    return None\n")
    with pytest.raises(ValueError, match=r"ast_optional.*scope"):
        _load_postpasses(
            cdir,
            [{"run": "_p.py:run", "ast_optional": True, "requires": ["scope"]}],
        )


# ── 2. 执行面 ──────────────────────────────────────────────


def _patch_decls(monkeypatch: pytest.MonkeyPatch, decls: list[dict]) -> None:
    import core.plugin_loader as pl

    monkeypatch.setattr(pl, "get_analyzer_postpass_decls", lambda: decls)


def test_analyze_file_facts_runs_only_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 AST 模式只跑 ast_optional 的 postpass；普通 postpass 与 L1 规则不跑。"""
    seen: list[str] = []

    def _report(analyzer, context):
        seen.append("optional")
        context.report("宏调用点诊断", code="T001", level="warning")

    _patch_decls(
        monkeypatch,
        [
            {"name": "a", "fn": _report, "requires": [], "produces": [], "ast_optional": True},
            {"name": "b", "fn": lambda a, c: seen.append("normal"), "requires": [], "produces": []},
        ],
    )
    analyzer = AnalysisTraversal({})
    analyzer._external_extra["fact"] = 1  # noqa: SLF001 — 单测直接驱动事实注入
    analyzer.analyze_file_facts()
    assert seen == ["optional"]
    assert [d.code for d in analyzer.diagnostics] == ["T001"]
    # 注入的事实键在 extra 里可见（postpass 的输入面）
    assert analyzer.context.extra["fact"] == 1
    # 无 AST 失败也记录下来（链也是时点；**不含** check_rules 链尾）
    assert [t["name"] for t in analyzer.postpass_trace] == ["a"]


def test_analyze_file_facts_keeps_scope_out_of_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 AST 模式没有 scope ⇒ 依赖 scope 的 requires 不得被当作已满足。"""
    _patch_decls(
        monkeypatch,
        [
            {
                "name": "needs_scope",
                "fn": lambda a, c: None,
                "requires": ["scope"],
                "produces": [],
                "ast_optional": True,
            }
        ],
    )
    analyzer = AnalysisTraversal({})
    analyzer._context = AnalysisContext()
    with pytest.raises(ValueError, match="requires 未满足"):
        analyzer.analyze_file_facts()
