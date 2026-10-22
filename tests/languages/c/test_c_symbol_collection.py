"""tests/languages/c/test_c_symbol_collection.py — C 符号收集产物（P1 首片）。

产物形状 = `{name, kind, scope, scope_kind, decl_order, decl_line, phase}`；用途、分期语义
（`pre_scan` 只作提示/对比、判定用 `analyze`）与默认偏置（未声明标识符 = `not typedef`，
显式化）见 `grammar/c/README.md`「符号收集产物」节与
`grammar/c/plugins/semantics/_api.py`（查询入口）。

判据（本文件）：① 正 `typedef int myint; myint v;`；② 负 `int myint;` ⇒ variable；
③ 声明顺序（使用在声明之前 ⇒ 非 typedef）；④ 作用域（块内 typedef 出块失效 + 内层遮蔽）；
⑤ 分期可区分（同名两期记录并存）；⑥ 产物只增不改（无新诊断 + postpass 只写 context）。

**读取入口**（测试/消费方）：`AnalysisTraversal(rules, rules_dir="grammar/c")` →
`analyze(ast)` → `_api.product_from(at)`（analyze 期）。
"""

import os

from analyzer.traversal import AnalysisTraversal
from grammar.c.plugins.semantics import _api

_RULES = "grammar/c"


def _reload_components() -> None:
    """补回 C 包的组件装载（按生产路径 `setup_grammar` → `load_all_components`）。

    ⚠ 测试隔离的已知面：`core.plugin_loader._loaded_components` 是**测试级**全局态
    （`core/global_state.py` TRACKED，策略"只去新增"），上一测试收尾会把本模块 fixture
    装载的 C 组件键删掉 ⇒ postpass 声明随之消失（原语注册表不还原，故符号收集本身仍在）。
    不补回则"产物写 context"这条判据会假红。handler 模块已在 `sys.modules` 命中，
    不会重复执行 `@register`。
    """
    from core.plugin_loader import load_all_components

    load_all_components(plugins_dir=os.path.join(_RULES, "plugins"))


def _analyze(c, src: str):
    """解析 + 语义分析（analyze pass）→ AnalysisTraversal（产物在其 context 上）。"""
    _reload_components()
    ast = c["parser"].parse(c["lexer"].tokenize(src))
    assert ast is not None, f"解析失败：{src!r}"
    at = AnalysisTraversal(c["rules"], rules_dir=_RULES)
    at.analyze(ast)
    return at


def _product_records(c, src: str):
    """(traversal, analyze 期记录)。"""
    at = _analyze(c, src)
    return at, _api.product_from(at)["records"]


def _only(records, phase: str) -> list[dict]:
    return [r for r in records if r["phase"] == phase]


class TestSymbolProduct:
    """六条判据：正 / 负 / 声明顺序 / 作用域 / 分期 / 只增不改。"""

    def test_positive_typedef_and_variable(self, c):
        """① 正：`typedef int myint; myint v;` ⇒ myint=typedef、v=variable。"""
        _, recs = _product_records(c, "typedef int myint;\nmyint v;\n")
        analyze = {(r["name"], r["kind"]): r for r in _only(recs, "analyze")}
        assert ("myint", "typedef") in analyze, analyze
        assert ("v", "variable") in analyze, analyze
        assert analyze[("myint", "typedef")]["scope"] == "<global>"
        assert analyze[("myint", "typedef")]["decl_line"] == 1
        assert _api.is_typedef("myint", recs) is True
        assert _api.is_typedef("v", recs) is False

    def test_negative_same_text_is_not_typedef(self, c):
        """② 负：同文本换符号表（`int myint;`）⇒ variable，**不得**判 typedef。"""
        _, recs = _product_records(c, "int myint;\nmyint *b;\n")
        analyze = [r for r in _only(recs, "analyze") if r["name"] == "myint"]
        assert [r["kind"] for r in analyze] == ["variable"], analyze
        assert _api.is_typedef("myint", recs) is False
        # 默认偏置：从未声明的名字同样不是 typedef（显式口径，见 DEFAULT_TYPEDEF_BIAS）
        assert _api.DEFAULT_TYPEDEF_BIAS == "not typedef"
        assert _api.is_typedef("never_declared", recs) is False

    def test_declaration_order_gates_use(self, c):
        """③ 声明顺序：使用在 typedef 声明之前 ⇒ 该位置不是 typedef 名。"""
        _, recs = _product_records(c, "myint v;\ntypedef int myint;\n")
        assert _api.is_typedef("myint", recs, at_line=1) is False, "第 1 行使用时尚未声明"
        assert _api.is_typedef("myint", recs, at_line=2) is True, "第 2 行声明后成立"
        analyze = {r["name"]: r for r in _only(recs, "analyze")}
        assert analyze["myint"]["decl_order"] > analyze["v"]["decl_order"], analyze

    def test_block_scope_expires(self, c):
        """④a 作用域：块内 typedef 出块失效（记录落在块作用域路径上）。"""
        _, recs = _product_records(c, "void f(void) {\n    typedef int t;\n}\nt v;\n")
        t_recs = [r for r in _only(recs, "analyze") if r["name"] == "t"]
        assert [r["scope"] for r in t_recs] == ["<global>/FuncDef/CompoundStmt"], t_recs
        assert _api.is_typedef("t", recs, scope="<global>") is False, "文件作用域无 t"
        assert _api.is_typedef("t", recs, scope="<global>/FuncDef/CompoundStmt") is True

    def test_inner_scope_shadows_outer(self, c):
        """④b 作用域：内层 typedef 遮蔽外层 ⇒ 两条记录、作用域路径不同。"""
        _, recs = _product_records(
            c, "typedef int t;\nvoid f(void) {\n    typedef char t;\n    t inner;\n}\n"
        )
        t_recs = [r for r in _only(recs, "analyze") if r["name"] == "t"]
        assert {r["scope"] for r in t_recs} == {
            "<global>",
            "<global>/FuncDef/CompoundStmt",
        }, t_recs
        assert all(r["kind"] == "typedef" for r in t_recs), t_recs
        assert _api.is_typedef("t", recs, scope="<global>") is True
        assert _api.is_typedef("t", recs, scope="<global>/FuncDef/CompoundStmt") is True

    def test_kinds_cover_tag_enumerator_function_param(self, c):
        """① 补充：kind 覆盖标签 / 枚举常量 / 函数 / 形参（首片要求的名字族）。"""
        _, recs = _product_records(
            c,
            "struct p { int x; };\nenum e { A, B };\nvoid g(int arg) {\n    int local;\n}\n",
        )
        kinds = {
            (r["name"], r["kind"], r["scope"])
            for r in _only(recs, "analyze")
        }
        assert ("p", "tag", "<global>") in kinds, kinds
        assert ("e", "tag", "<global>") in kinds, kinds
        assert ("A", "enumerator", "<global>") in kinds, kinds
        assert ("g", "function", "<global>/FuncDef") in kinds, kinds
        assert ("arg", "variable", "<global>/FuncDef") in kinds, kinds
        assert ("local", "variable", "<global>/FuncDef/CompoundStmt") in kinds, kinds

    def test_product_exposed_on_context_extra(self, c):
        """⑥ 落点：postpass 把产物写进 `context.extra`（读取入口的可验证证据）。"""
        at = _analyze(c, "typedef int myint;\n")
        product = at.context.extra.get(_api.PRODUCT_KEY)
        assert product is not None, "postpass 未把产物写进 context.extra"
        assert product["default_typedef_bias"] == _api.DEFAULT_TYPEDEF_BIAS
        assert [r["name"] for r in product["records"]] == ["myint"]
        # 公开读取入口与 context 内一致（`product_from` 缺失时才现场重建）
        assert _api.product_from(at)["records"] == product["records"]

    def test_collection_adds_no_diagnostics(self, c):
        """⑥ 只增不改：收集不新增诊断（重名静默跳过，不报 E001）。"""
        at, _ = _product_records(c, "typedef int myint;\nint x;\nint x;\nmyint v;\n")
        assert [(d.code, d.level) for d in at.diagnostics] == [], at.diagnostics
