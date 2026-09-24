"""语言切换 = 重建语言作用域（单语言选择模型）：同进程跑两种语言不互相串味。

背景（2026-09-14 实测）：同进程「先跑 c4 管线 → 再跑 verilog」→ verilog 输出变
**空**且 `success=True`（保真度 0.9925 → 0.0000）。根因是语言作用域状态跨语言累积：

1. `GrammarRulesRegister.get_default()` 只增不清 → 后一语言 `setup_grammar` 返回的
   rules 字典里混入前一语言规则**且顺序靠前**；`RuleSelector.get_block_rule()` 取
   "第一个匿名块规则" → **根规则被前一语言夺走**（verilog 源码被按 c4 的 `Program`
   解析）；
2. `transform.engine._plugin_registry` 累积 → 前一语言的 transform 插件参与本语言
   管线（`AsmGenPlugin` 的根守卫恰好被 ① 造成的 `Program` 根通过 → AST 被换掉）。

这两条合起来就是一直没定性的那类"幽灵"：xdist 动态分发决定"同 worker 里先跑过
哪个语言"，于是同一份源码时而正常、时而保真度掉档。

守护：`GrammarRulesRegister.begin_language()` 切语言即重置规则表；
`transform.engine.active_plugin_classes()` 按当前语言作用域过滤插件。
"""

import difflib

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from parser import setup_grammar
from parser.rule_selector import RuleSelector
from transform.engine import active_plugin_classes
from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

_C4_SRC = "int main() { int x; x = 1; return x; }"
_VERILOG_REF = "tests/e2e/samples/macro/ref/ref_pp_func_macro_stmt.v"
_VERILOG_SRC = "module m;\n  wire a;\n  assign a = 1'b0;\nendmodule\n"
_FIDELITY_THRESHOLD = 0.99

# c4 独有规则名（verilog 语言包里不存在——切换后不得残留）
_C4_ONLY_RULES = ("FuncDef", "VarDecl")


def _strip_all(text: str) -> str:
    lines = []
    for line in text.splitlines():
        ci = line.find("//")
        if ci >= 0:
            line = line[:ci]
        lines.append(line)
    return "".join("".join(lines).split())


def _pipe(source: str, **kw) -> dict:
    return run_pipeline_on_source(source=source, quiet=True, **kw)


def _run_c4() -> dict:
    res = _pipe(_C4_SRC, rules_dir="grammar/c4")
    assert res["success"], res.get("error")
    assert "ENT" in (res.get("output") or ""), "c4 汇编生成未生效"
    return res


def _run_verilog_macro() -> tuple[str, str, float]:
    with open(_VERILOG_REF, encoding="utf-8") as f:
        src = f.read()
    res = _pipe(src, expand_macros=True, no_lint=True)
    assert res["success"], res.get("error")
    out = res.get("output") or ""
    ratio = difflib.SequenceMatcher(None, _strip_all(src), _strip_all(out)).ratio()
    return out, getattr(res.get("ast"), "node_name", ""), ratio


# ── 端到端：同进程两种语言 ──────────────────────────────────────────────────

def test_verilog_after_c4_same_process() -> None:
    """先 c4 再 verilog：verilog 输出不被串味（曾经输出恒空）。"""
    _run_c4()
    out, root, ratio = _run_verilog_macro()
    assert out, "verilog 输出为空——语言作用域串味（根规则被前一语言夺走）"
    assert ratio >= _FIDELITY_THRESHOLD, f"保真度 {ratio:.4f} < {_FIDELITY_THRESHOLD}"
    assert root == "Root", f"根节点应为 verilog 的 Root，实际 {root!r}"


def test_c4_after_verilog_same_process() -> None:
    """反方向同样成立：先 verilog 再 c4，c4 汇编生成仍正确。"""
    res_v = _pipe(_VERILOG_SRC, no_lint=True)
    assert res_v["success"], res_v.get("error")
    _run_c4()


def test_alternating_languages_stay_correct() -> None:
    """来回切换：每次都以"当前语言"重新建立作用域。"""
    for _ in range(2):
        _run_c4()
        _, root, ratio = _run_verilog_macro()
        assert root == "Root" and ratio >= _FIDELITY_THRESHOLD


# ── 机制层：规则表 / 根规则 / 插件作用域 ────────────────────────────────────

def test_register_does_not_accumulate_across_languages() -> None:
    """切语言 = 重建规则表：前一语言独有规则不得残留（顺序也不得靠前）。"""
    setup_grammar("grammar/c4", GrammarRulesRegister.get_default())
    c4_rules = GrammarRulesRegister.get_default().rules
    assert set(_C4_ONLY_RULES) <= set(c4_rules), "前置条件：c4 规则应已注册"

    rules = setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())
    leaked = sorted(set(_C4_ONLY_RULES) & set(rules))
    assert not leaked, f"verilog 规则表残留前一语言规则：{leaked}"


def test_root_rule_belongs_to_current_language() -> None:
    """根规则由当前语言决定（历史上被 c4 的 Program 夺走 → 输出为空）。"""
    setup_grammar("grammar/c4", GrammarRulesRegister.get_default())
    rules = setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())
    stmt_names = [
        n for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    root = RuleSelector(rules, stmt_names).get_block_rule()
    assert root != "Program", "根规则被前一语言（c4 的 Program）夺走"
    assert root in rules, f"根规则 {root!r} 不在当前规则表内"


def test_plugin_scope_excludes_other_language() -> None:
    """插件应用按语言作用域：切到 verilog 后，c4 的插件不再参与。"""
    setup_grammar("grammar/c4", GrammarRulesRegister.get_default())
    c4_names = {cls.__name__ for cls in active_plugin_classes()}
    assert "AsmGenPlugin" in c4_names, "前置条件：c4 装载后其插件应在作用域内"

    setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())
    v_names = {cls.__name__ for cls in active_plugin_classes()}
    assert "AsmGenPlugin" not in v_names, "切到 verilog 后 c4 插件仍在作用域内"
    # 引擎插件（无语言归属）任何语言下都在
    assert {"SemanticMappingPlugin", "ConfigDrivenTransform"} <= v_names


def test_config_entries_follow_language() -> None:
    """配置声明随语言包重建（`plugins.render` 是 c4 独有节）。"""
    ConfigRegistry.load_language("grammar/c4")
    assert "plugins.render" in ConfigRegistry._entries
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )
    assert "plugins.render" not in ConfigRegistry._entries, "配置声明跨语言残留"


def test_component_load_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """装载期异常不被吞（fail-fast）：此前 `except ImportError: pass` 会把装载
    失败静默掉，语言作用域停在上一语言（实测症状：切到 verilog 后 c4 的
    `AsmGenPlugin` 仍在 `active_plugin_classes()` 内、组件规则缺失）。
    与"配置加载 fail-fast，不静默降级"硬约束一致。
    """
    import core.plugin_loader as pl

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        del args, kwargs  # 桩签名参数
        raise ImportError("boom")

    monkeypatch.setattr(pl, "load_all_components", _boom)
    with pytest.raises(ImportError, match="boom"):
        setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())
    # 恢复：setup_grammar 已清空 _loaded_components 后失败 → 撤桩重新装载，
    # 避免影响同文件后续用例
    monkeypatch.undo()
    setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())


def test_registry_truncation_does_not_misplace_plugin_origin() -> None:
    """幽灵 flake 回归：注册表被截断后新注册插件的**来源不得错配**。

    测试侧清理惯用 `del _plugin_registry[order:]`（5 处），但**只截注册表**。来源
    表若做成与注册表平行的下标表，则"注册 → 截断 → 再注册"之后 `zip` 会把后注册项
    的来源配到**前一项**上：语言插件配到 `None`（= 引擎插件语义）→ 在**任何**语言下
    都生效，正是"切到 verilog 后 c4 的 `AsmGenPlugin` 仍在 `active_plugin_classes()`
    内"这条长期未定性的幽灵；反向配错则会把引擎插件静默过滤掉。

    本测试显式制造该窗口：先注册一个**引擎来源**（None）探针 → 截断注册表 →
    再注册一个**语言来源**（asm_gen）探针 → 断言后者在当前语言下被过滤掉。
    """
    import transform.engine as e
    from grammar.c4.plugins.asm_gen._asm import AsmGenPlugin

    class _EngineProbe(e.TransformPlugin):
        """引擎侧来源（模块路径不在 grammar/plugins 下 → 判定为 None）。"""

        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            del root_scope  # 探针不参与执行，只为占一个注册位
            return ast

    class _LangProbe(AsmGenPlugin):
        """语言插件来源：借真实 c4 插件模块的 `__file__` 判定为 `asm_gen`。"""

    _LangProbe.__module__ = AsmGenPlugin.__module__

    order = len(e._plugin_registry)
    try:
        e.register_plugin(name="_probe_engine_origin")(_EngineProbe)
        del e._plugin_registry[order:]  # 模拟其它测试的清理：只截注册表
        e.register_plugin(name="_probe_lang_origin")(_LangProbe)  # 截断后再注册

        setup_grammar("grammar/verilog", GrammarRulesRegister.get_default())
        names = {cls.__name__ for cls in active_plugin_classes()}
        assert "_LangProbe" not in names, (
            "语言插件的来源被错配成引擎插件（None）→ 在任何语言下都生效"
        )
    finally:
        del e._plugin_registry[order:]
