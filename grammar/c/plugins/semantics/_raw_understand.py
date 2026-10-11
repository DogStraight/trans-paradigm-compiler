"""_raw_understand.py — P4 理解路径 · **analyzer 段「理解」**（C 包）。

作者定调的两段协作第一段：**理解 = 分析过程**——判"这段该被理解成什么结构"，产出结论；
改树由 transform 段（`_raw_transform.py`）执行。

本段对每个 raw 节点做三件事：
1. **语义确认（不得绕过既有校验）**：主门 = 遍历期既有 P4 校验
   `analyzer/primitives/_raw_validate.py::validate_raw_statement`（作用域精确；不过 ⇒ `E002`
   + 停管线，本段拿不到管线）。本段只做**加强性**二次确认：该名在**完整**符号产物里确有
   类型名类记录（`_p4_query.TYPE_NAME_KINDS`）——作用域精确判定不在这里重复（postpass 期
   作用域链已不可得，重复实现只会引入第二套口径）。
2. **结构选定**：候选子树 `raw_candidate` 里须出现包声明的确定结构
   （`UNDERSTOOD_STRUCTURES`），且该结构的类型名叶子文本必须等于位点名
   （`raw_substituted[0]["original_text"]` 已还原为源码原文）——"这段被理解成了什么"由此确定。
3. **落档**：结论挂节点属性 `raw_understand`（transform 段据此改树）；同时进产物
   `context.extra["c_raw_understanding"]`（可视化/trace 用）。

**静默边界（有意）**：候选缺失（如 `(t){1}` 复合字面量：承载期建候选失败）或候选里找不到
包声明的确定结构 ⇒ 只记 `ok=False` + 原因，**不报错**（raw 仍走 verbatim 直出，行为与
本批之前一致；这是"承载期未覆盖"的诚实边界，不是理解段的失败）。
唯一会报错（`E003`）的是**不一致**：遍历期 P4 已放行、但完整符号产物说该名不是类型名，
或候选/取证自相矛盾——这类绝不静默。

Doc: `grammar/c/README.md`「P4 理解路径（两段协作）」/ `docs/gaps/gap-c-semantic-base.md`
"""
from __future__ import annotations

from typing import Any

from core.define import Node, iter_nodes
from analyzer.raw_contract import RAW_STATEMENT_NODE_NAME
from grammar.c.plugins.semantics import _api, _p4_query

#: 理解结论属性（transform 段读）
UNDERSTAND_ATTR = "raw_understand"
#: 承载期给的候选结构属性与取证属性（第一步契约）
CANDIDATE_ATTR = "raw_candidate"
EVIDENCE_ATTR = "raw_substituted"
#: 理解结论产物键（`context.extra`）
UNDERSTANDING_PRODUCT_KEY = "c_raw_understanding"
#: 不一致（不是"未覆盖"）时的诊断码
INCONSISTENT_CODE = "E003"

#: **包声明的确定结构**（C 语言知识）：候选子树里出现其中之一，才算"这段被理解成了什么"。
#: 语言知识在包侧（同 `_p4_query` 的 kind 常量口径），引擎不认识任何结构名。
UNDERSTOOD_STRUCTURES: tuple[str, ...] = ("CastExpr", "CompoundLiteralExpr")


def _names_of(node: Node) -> list[str]:
    raw = getattr(node, "raw_names", None)
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, (list, tuple)):
        return [n for n in raw if isinstance(n, str) and n]
    return []


def _type_text_of(structure: Node) -> list[str]:
    """确定结构子树里的**类型名文本**（叶子值与 `Identifier.content` 两侧取）。"""
    texts: list[str] = []
    for sub in iter_nodes(structure):
        for key in ("content", "value", "name"):
            val = getattr(sub, key, None)
            if isinstance(val, str) and val:
                texts.append(val)
    return texts


def _select_structure(candidate: Node, names: list[str]) -> tuple[str, str]:
    """候选子树里选确定结构 → `(结构名, 类型名文本)`；找不到 → `("", "")`。"""
    for structure in iter_nodes(candidate):
        if structure.node_name not in UNDERSTOOD_STRUCTURES:
            continue
        texts = _type_text_of(structure)
        for name in names:
            if name in texts:
                return structure.node_name, name
    return "", ""


def _type_name_records(product: dict) -> set[str]:
    """完整符号产物里的"类型名类"名字集合（`analyze` 期）。"""
    return {
        str(r.get("name"))
        for r in (product.get("records") or [])
        if r.get("kind") in _p4_query.TYPE_NAME_KINDS
        and r.get("phase") == _api.PHASE_ANALYZE
    }


def run_raw_understanding(analyzer: Any, context: Any) -> dict:
    """postpass：给 raw 节点挂理解结论（`requires = ["c_symbols"]` 保证产物齐备）。

    返回结论摘要（`{"understood": [...], "not_understood": [...], "inconsistent": [...]}`）；
    产物入口 `run_raw_understanding_product` 会把它写进
    `context.extra[UNDERSTANDING_PRODUCT_KEY]`。
    """
    ast = getattr(analyzer, "_ast", None)
    if not isinstance(ast, Node):
        return {"understood": [], "not_understood": [], "inconsistent": []}

    product = _api.product_from(analyzer, context)
    type_names = _type_name_records(product)
    understood: list[dict] = []
    not_understood: list[dict] = []
    inconsistent: list[dict] = []

    for node in iter_nodes(ast):
        if node.node_name != RAW_STATEMENT_NODE_NAME:
            continue
        names = _names_of(node)
        candidate = getattr(node, CANDIDATE_ATTR, None)
        evidence = getattr(node, EVIDENCE_ATTR, None)
        site = {
            "line": getattr(node, "raw_line", None),
            "column": getattr(node, "raw_column", None),
            "order": getattr(node, "raw_order", None),
        }
        if not isinstance(candidate, Node):
            # 承载期未覆盖（如复合字面量）：记原因，不报错（raw 直出，行为不变）
            not_understood.append({"reason": "candidate_missing", "names": names, **site})
            continue
        missing = [n for n in names if n not in type_names]
        if missing:
            # 不一致：遍历期 P4 放行、完整产物却无类型名记录 ⇒ 绝不静默
            inconsistent.append({"reason": "name_not_confirmed", "names": missing, **site})
            continue
        structure, type_text = _select_structure(candidate, names)
        if not structure:
            not_understood.append(
                {
                    "reason": "structure_not_found",
                    "names": names,
                    "candidate": candidate.node_name,
                    **site,
                }
            )
            continue
        first = evidence[0] if isinstance(evidence, list) and evidence else {}
        if not isinstance(first, dict) or str(first.get("original_text", "")) not in names:
            inconsistent.append({"reason": "evidence_inconsistent", "names": names, **site})
            continue
        node.add_attr(
            UNDERSTAND_ATTR,
            {
                "ok": True,
                "structure": structure,
                "statement": candidate.node_name,
                "type_text": type_text,
                "names": list(names),
                "rule": str(first.get("rule", "")),
            },
        )
        understood.append(
            {
                "structure": structure,
                "statement": candidate.node_name,
                "type_text": type_text,
                "names": list(names),
                **site,
            }
        )

    for item in inconsistent:
        # 只在"没有其它错误"时报错：负样本（遮蔽/声明序）已由 E002 停管线，避免重复噪音
        if getattr(analyzer, "has_errors", False):
            continue
        context.report(
            f"raw 段理解不一致（{item['reason']}）：{', '.join(item.get('names') or [])}",
            code=INCONSISTENT_CODE,
            level="error",
        )
    return {"understood": understood, "not_understood": not_understood, "inconsistent": inconsistent}


def run_raw_understanding_product(analyzer: Any, context: Any) -> dict:
    """产物入口：结论摘要写 `context.extra[UNDERSTANDING_PRODUCT_KEY]` 并返回之。"""
    summary = run_raw_understanding(analyzer, context)
    context.extra[UNDERSTANDING_PRODUCT_KEY] = summary
    return summary
