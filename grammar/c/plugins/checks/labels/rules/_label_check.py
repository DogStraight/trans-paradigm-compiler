"""_label_check.py — C 标签与 switch 标签语义（LAB001–LAB003）的 postpass 实现。

形态（task-40 方案实测确认）：**postpass 走 AST**，不是 `[[checks]]` 符号分发——
label/goto 不进符号表（`analyzer.all_symbols` 只有函数），没有 `sym.kind` 可承接。

引擎接口（实测）：
  · AST 入口 = `analyzer._ast`（⚠ `AnalysisContext` **没有** `ast` 字段，`vars(context)` 实测
    只有 config/diagnostics/extra/node/root_scope/scope）；
  · `context.report(msg, code=..., level=..., node=...)` 生效，并按 postpass 计入 `postpass_trace`；
  · 规则数据 = `core.check_registry.get_check_rules()`；激活集 = `analyzer.checks.active_rule_ids(analyzer)`
    （引擎注释即写明"postpass 插件复用同一激活逻辑"）。

**语言知识（节点名/字段名）集中在下列包侧常量**（先例 `_api.SC_NODE_NAMES`；
组件 `tpc.toml` 的自定义段不会被引擎读取，故不写自定义段）。**实测形状**：
  `FuncDef.body` = CompoundStmt；`LabelStmt`：`name`(Identifier)+`stmt`；
  `GotoStmt`：`label`(Identifier)；`CaseLabel`(`value`)/`DefaultLabel` 是独立节点；
  `SwitchStmt.body` = CompoundStmt。

三条硬要求（判据锁定）：
  1. **只收 `LabelStmt`** —— `case`/`default` 不得当普通 label（语料 `ring_buffer.c` 同文件
     既有 `done:` 又有 `default:`；实证整文件 LabelStmt=1、DefaultLabel=1）；
  2. **前向 goto 用两遍扫描** —— 先收全函数内 label，再判 goto 目标；
  3. **按函数分组** —— label 具函数作用域（跨块可见），不同函数同名 label 合法。

另写 `context.extra["c_labels"]`（观测产物：函数内标签/跳转摘要 + 违规清单）。

Doc: `grammar/c/README.md`「标签与 goto 语义（LAB）」/ 规则表 `rules/labels.toml` 头注（条款引文与档位）
"""
from __future__ import annotations

from typing import Any

# ── 包侧语言知识常量（节点名 / 字段名 / 规则 id / 产物键）────────────────
FUNC_NODE = "FuncDef"
FUNC_NAME_FIELD = "declarator"
LABEL_NODE = "LabelStmt"
LABEL_NAME_FIELD = "name"
GOTO_NODE = "GotoStmt"
GOTO_TARGET_FIELD = "label"
CASE_NODE = "CaseLabel"
DEFAULT_NODE = "DefaultLabel"
SWITCH_NODE = "SwitchStmt"
CONTENT_FIELD = "content"

LAB001 = "LAB001"  # 同函数内 label 名唯一
LAB002 = "LAB002"  # goto 目标须在本函数内
LAB003 = "LAB003"  # case/default 只能在 switch 内
LAB_IDS = (LAB001, LAB002, LAB003)

PRODUCT_KEY = "c_labels"


def _text(node: Any) -> str | None:
    """Identifier 节点的名字（`content`）；缺省/非字符串 ⇒ None。"""
    if node is None:
        return None
    val = getattr(node, CONTENT_FIELD, None)
    return val if isinstance(val, str) and val else None


def _fill(template: Any, name: str) -> str:
    """规则 message 模板的 `{name}` 填充（规则=数据；未知占位符原样保留）。"""
    tpl = template if isinstance(template, str) and template else name
    return tpl.replace("{name}", name)


def _active_rules(analyzer: Any) -> dict[str, dict]:
    """读取**已激活**的 LAB 规则（id → 规则表条目）。

    `active_rule_ids` 是引擎为 postpass 插件预留的同一激活逻辑（default + 用户 enabled/overrides）；
    规则表用引擎自己的插件目录解析入口读（`get_check_rules()` 的**默认**目录不是本包目录，
    实测返回空表 ⇒ 必须显式传目录）。
    """
    from analyzer.checks import _plugins_dir_of, active_rule_ids
    from core.check_registry import get_check_rules

    active = active_rule_ids(analyzer)
    out: dict[str, dict] = {}
    for rule in get_check_rules(_plugins_dir_of(analyzer)):
        rid = rule.get("id")
        if rid in LAB_IDS and rid in active:
            out[rid] = rule
    return out


def _function_names(analyzer: Any) -> dict[int, str]:
    """函数节点 id → 符号名（复用符号基座：`FuncDef` 位的符号 `decl_node` 即该节点）。"""
    out: dict[int, str] = {}
    for sym in getattr(analyzer, "all_symbols", None) or []:
        if getattr(sym, "kind", None) != "function":
            continue
        node = getattr(sym, "decl_node", None)
        if node is not None:
            out[id(node)] = str(sym.name)
    return out


def _functions(root: Any, names: dict[int, str]) -> list[tuple[str, Any]]:
    """文件内全部函数（名, FuncDef 节点）。C 无嵌套函数 ⇒ 顶层扫描即可。"""
    from core.define import iter_nodes

    out: list[tuple[str, Any]] = []
    for node in iter_nodes(root):
        if node.node_name == FUNC_NODE:
            out.append((names.get(id(node), "<anon>"), node))
    return out


def _collect(
    node: Any,
    inside_switch: bool,
    labels: dict[str, list[Any]],
    gotos: list[tuple[str, Any]],
    outside_switch: list[Any],
) -> None:
    """递归收集：label 定义（按名分组、保源序）、goto 目标、switch 之外的 case/default。

    `inside_switch` 标志跨块传播（Duff's device：switch 体 → do/while → case 合法）；
    遇到 `SwitchStmt` 时进入其子树并把标志置真。
    """
    for child in node.iter_children():
        name = child.node_name
        if name == LABEL_NODE:
            label = _text(getattr(child, LABEL_NAME_FIELD, None))
            if label:
                labels.setdefault(label, []).append(child)
        elif name == GOTO_NODE:
            target = _text(getattr(child, GOTO_TARGET_FIELD, None))
            if target:
                gotos.append((target, child))
        elif name == SWITCH_NODE:
            _collect(child, True, labels, gotos, outside_switch)
            continue
        elif name in (CASE_NODE, DEFAULT_NODE) and not inside_switch:
            outside_switch.append(child)
        _collect(child, inside_switch, labels, gotos, outside_switch)


def run_label_checks(analyzer: Any, context: Any) -> None:
    """postpass 入口：按函数判定 label 唯一性 / goto 目标 / case-default 位置。"""
    root = getattr(analyzer, "_ast", None)
    rules = _active_rules(analyzer)
    product: dict[str, Any] = {"functions": [], "violations": []}
    context.extra[PRODUCT_KEY] = product
    if root is None:
        return

    def report(rule_id: str, display: str, node: Any, why: str) -> None:
        rule = rules.get(rule_id)
        if not rule:
            return
        context.report(
            _fill(rule.get("message"), display),
            code=rule_id,
            level=str(rule.get("severity", "warning")),
            node=node,
        )
        product["violations"].append(
            {"code": rule_id, "name": display, "line": getattr(node, "_pos_line", None), "why": why}
        )

    for func_name, func in _functions(root, _function_names(analyzer)):
        labels: dict[str, list[Any]] = {}
        gotos: list[tuple[str, Any]] = []
        outside_switch: list[Any] = []
        _collect(func, False, labels, gotos, outside_switch)

        # ── LAB001：同函数内 label 名唯一（第 2..n 处各报一条）──
        for label, nodes in labels.items():
            for dup in nodes[1:]:
                report(LAB001, label, dup, "duplicate-label")

        # ── LAB002：goto 目标须在本函数内（labels 已收齐 ⇒ 前向 goto 合法）──
        for target, node in gotos:
            if target not in labels:
                report(LAB002, target, node, "undefined-goto")

        # ── LAB003：case/default 只能出现在 switch 内 ──
        for node in outside_switch:
            display = "default" if node.node_name == DEFAULT_NODE else "case"
            report(LAB003, display, node, "label-outside-switch")

        product["functions"].append(
            {
                "name": func_name,
                "labels": sorted(labels),
                "gotos": [target for target, _ in gotos],
                "outside_switch": len(outside_switch),
            }
        )
