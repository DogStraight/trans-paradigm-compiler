"""tests/engine/analyzer/test_p4_raw_understanding.py — P4 理解路径两段的**单元判据**。

- analyzer 段（理解）：`grammar/c/plugins/semantics/_raw_understand.py::run_raw_understanding`
- transform 段（改树）：`grammar/c/plugins/semantics/_raw_transform.py::RawPromotePlugin`

用**构造的** raw 节点（8 条契约字段 + `raw_candidate` + `raw_substituted`）跑，不依赖管线：
  · 理解成功 ⇒ 结论 `raw_understand` 落档（结构/类型名文本/规则）；
  · 候选缺失 ⇒ 只记 `candidate_missing`、**不报错**（承载期未覆盖的诚实边界）；
  · 候选里无包声明的确定结构 ⇒ 记 `structure_not_found`、不报错；
  · 遍历期已放行但完整产物说该名不是类型名 ⇒ **报 E003**（不一致，不静默）；
  · 改树 ⇒ `sub_node = [raw_candidate]`、幂等（二次运行零改动）、
    无结论不提升、`iter_children()` 去重 ⇒ 候选**恰好**被遍历一次。
"""

from core.define import CHILDREN_FIELD, Node, iter_nodes
from grammar.c.plugins.semantics import _raw_understand as ru
from grammar.c.plugins.semantics._raw_transform import RawPromotePlugin

RAW = "RawStatement"


class _StubContext:
    """最小 context：`extra`（产物面）+ `report`（收集诊断）。"""

    def __init__(self, records: list[dict]) -> None:
        self.extra: dict = {"c_symbols": {"records": records, "phases": {}}}
        self.diagnostics: list[dict] = []

    def report(self, message: str, code: str = "", level: str = "error", node=None) -> None:
        self.diagnostics.append({"message": message, "code": code, "level": level, "node": node})


class _StubAnalyzer:
    """最小 analyzer：postpass 只读 `_ast` / `has_errors` / `all_symbols`（本例走产物面）。"""

    def __init__(self, ast: Node, *, has_errors: bool = False) -> None:
        self._ast = ast
        self.has_errors = has_errors
        self.all_symbols: list = []


def _candidate(structure: str = "CastExpr", type_text: str = "myint") -> Node:
    """构造候选子树：`ExprStmt → 结构(CastExpr) → 类型名叶子`。"""
    leaf = Node("id")
    leaf.add_attr("value", type_text)
    type_name = Node("SimpleType")
    type_name.add_attr("base", leaf)
    struct = Node(structure)
    struct.add_attr("type_name", type_name)
    stmt = Node("ExprStmt")
    stmt.add_attr("expr", struct)
    return stmt


def _raw_node(*, with_candidate: bool = True, candidate: Node | None = None) -> Node:
    node = Node(RAW)
    node.add_attr("_verbatim_text", "x = (myint)y;")
    node.add_attr("_tok_span", (0, 5))
    node.add_attr("raw_names", ["myint"])
    node.add_attr("raw_line", 2)
    node.add_attr("raw_column", 20)
    node.add_attr("raw_order", 4)
    node.add_attr("raw_reason", "not-converged")
    node.add_attr("raw_eligible", True)
    if with_candidate:
        node.add_attr(ru.CANDIDATE_ATTR, candidate if candidate is not None else _candidate())
        node.add_attr(
            ru.EVIDENCE_ATTR,
            [
                {
                    "index": 4,
                    "line": 2,
                    "column": 20,
                    "original_type": "id",
                    "original_text": "myint",
                    "substituted_as": "keyword.int",
                    "restored_leaves": 1,
                    "rule": "ExprStmt",
                }
            ],
        )
    return node


def _typedef_record(name: str = "myint") -> dict:
    return {"name": name, "kind": "typedef", "phase": "analyze", "scope": "<global>"}


def _run_understanding(root: Node, records: list[dict], *, has_errors: bool = False):
    ctx = _StubContext(records)
    analyzer = _StubAnalyzer(root, has_errors=has_errors)
    summary = ru.run_raw_understanding_product(analyzer, ctx)
    return summary, ctx


class TestUnderstandingSegment:
    def test_understood_conclusion_lands_on_node(self):
        raw = _raw_node()
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        summary, ctx = _run_understanding(root, [_typedef_record()])
        assert not ctx.diagnostics, ctx.diagnostics
        assert summary["understood"] and not summary["not_understood"], summary
        conclusion = getattr(raw, ru.UNDERSTAND_ATTR)
        assert conclusion["ok"] is True
        assert conclusion["structure"] == "CastExpr"
        assert conclusion["statement"] == "ExprStmt"
        assert conclusion["type_text"] == "myint"
        assert conclusion["names"] == ["myint"]
        assert ctx.extra[ru.UNDERSTANDING_PRODUCT_KEY] is summary

    def test_candidate_missing_is_recorded_not_an_error(self):
        """承载期未覆盖（如复合字面量）⇒ 记原因、不报错（行为与本批之前一致）。"""
        raw = _raw_node(with_candidate=False)
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        summary, ctx = _run_understanding(root, [_typedef_record()])
        assert not ctx.diagnostics, ctx.diagnostics
        assert summary["not_understood"][0]["reason"] == "candidate_missing", summary
        assert getattr(raw, ru.UNDERSTAND_ATTR, None) is None

    def test_structure_not_found_is_recorded_not_an_error(self):
        """候选里没有包声明的确定结构 ⇒ 不提升、也不报错（不是"不一致"）。"""
        raw = _raw_node(candidate=_candidate("SomeOtherNode"))
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        summary, ctx = _run_understanding(root, [_typedef_record()])
        assert not ctx.diagnostics, ctx.diagnostics
        assert summary["not_understood"][0]["reason"] == "structure_not_found", summary

    def test_unconfirmed_name_reports_e003(self):
        """遍历期放行但完整产物说该名不是类型名 ⇒ E003（不一致绝不静默）。"""
        raw = _raw_node()
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        summary, ctx = _run_understanding(root, [{"name": "myint", "kind": "variable"}])
        assert summary["inconsistent"][0]["reason"] == "name_not_confirmed", summary
        assert [d["code"] for d in ctx.diagnostics] == [ru.INCONSISTENT_CODE], ctx.diagnostics
        assert getattr(raw, ru.UNDERSTAND_ATTR, None) is None

    def test_unconfirmed_name_is_quiet_when_other_errors_exist(self):
        """负样本（遮蔽）已由 E002 停管线 ⇒ 本段不再叠加噪音。"""
        raw = _raw_node()
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        _, ctx = _run_understanding(
            root, [{"name": "myint", "kind": "variable"}], has_errors=True
        )
        assert ctx.diagnostics == []


class TestTransformSegment:
    def _root_with(self, raw: Node) -> Node:
        root = Node("TranslationUnit")
        root.add_attr("sub_node", [raw])
        return root

    def test_promotes_candidate_into_sub_nodes(self):
        raw = _raw_node()
        raw.add_attr(ru.UNDERSTAND_ATTR, {"ok": True, "structure": "CastExpr"})
        candidate = getattr(raw, ru.CANDIDATE_ATTR)
        root = self._root_with(raw)
        plugin = RawPromotePlugin()
        out = plugin.process(root, None)
        assert out is root
        assert getattr(raw, CHILDREN_FIELD) == [candidate]
        assert plugin.stats == {"raw_promoted": 1}
        assert getattr(raw, "_verbatim_text") == "x = (myint)y;"  # 渲染权威保留

    def test_no_conclusion_means_no_promotion(self):
        raw = _raw_node()  # 无 raw_understand
        root = self._root_with(raw)
        plugin = RawPromotePlugin()
        plugin.process(root, None)
        assert getattr(raw, CHILDREN_FIELD, None) in (None, [])
        assert plugin.stats == {"raw_promoted": 0}

    def test_promotion_is_idempotent(self):
        raw = _raw_node()
        raw.add_attr(ru.UNDERSTAND_ATTR, {"ok": True})
        root = self._root_with(raw)
        plugin = RawPromotePlugin()
        plugin.process(root, None)
        first = list(getattr(raw, CHILDREN_FIELD))
        plugin.process(root, None)
        assert getattr(raw, CHILDREN_FIELD) == first
        assert plugin.stats == {"raw_promoted": 0}

    def test_candidate_visited_exactly_once_after_promotion(self):
        """`iter_children()` 按 id 去重：候选同时挂 `raw_candidate` 与 `sub_node` 也只遍历一次。"""
        raw = _raw_node()
        raw.add_attr(ru.UNDERSTAND_ATTR, {"ok": True})
        root = self._root_with(raw)
        RawPromotePlugin().process(root, None)
        names = [n.node_name for n in iter_nodes(root)]
        assert names.count("ExprStmt") == 1, names
        assert names.count("CastExpr") == 1, names
        assert names.count(RAW) == 1, names

    def test_verbatim_authority_survives_promotion(self):
        """带子节点 + `_verbatim_text` ⇒ 渲染权威仍是 verbatim（渲染端到端见语言包测试）。"""
        raw = _raw_node()
        raw.add_attr(ru.UNDERSTAND_ATTR, {"ok": True})
        root = self._root_with(raw)
        RawPromotePlugin().process(root, None)
        assert getattr(raw, "_verbatim_text") == "x = (myint)y;"
        assert getattr(raw, CHILDREN_FIELD), "子树应已提升"
        assert getattr(raw, ru.CANDIDATE_ATTR) is getattr(raw, CHILDREN_FIELD)[0]
