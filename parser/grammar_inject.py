"""语法规则注入 — production 注入、传播与替换。

支持目标寻址语法：RuleName.production[N]。
注入改为结构化：analyze → 树层合并（choice 候选插入 / call 替换）→ serialize
回字符串，替代字符串正则/子串操作。fail-fast 对齐 ADR-0003：inject 路径
target 规则缺失或 production 无法解析直接报错，不静默降级；replace 路径
对缺失规则仅警告跳过（软，兼容旧配置）。
Doc: docs/language_walkthrough.md（EXT 注入）
"""

import re
from collections.abc import Mapping
from typing import Any

from core.errors import GrammarError
from .rule_selector import (
    analyze_production_features,
    insert_choice_candidate,
    make_call_feature,
    replace_calls,
    serialize_production_tree,
)


def _parse_target(target: str) -> tuple[str, str, int]:
    m = re.match(r"^@?(\w+)(?:\.(\w+))?(?:\[(\d+)\])?$", target)
    if not m:
        return target.lstrip("@"), "production", 0
    return m.group(1), m.group(2) or "production", int(m.group(3)) if m.group(3) else 0


_VERBOSE = False


def _write_prods(rule: Any, prods: list) -> None:
    """统一写回 production；块规则同步重算 block_prods。

    block_prods 是块规则自身 production 去掉首尾字面 token 的元素列表（非递归
    展开）——子规则 production 变化由规则表动态解析，block_prods 不随子规则同步
    （这是设计，不是"重算一半"）。_resync_block_parts 只处理"块规则自身 production
    被改写首尾"的场景。
    """
    object.__setattr__(rule, "production", tuple(prods))
    if getattr(rule, "is_block", False):
        _resync_block_parts(rule)


def _resync_block_parts(rule: Any) -> None:
    """块规则 block_start/block_end/block_prods 重算（对齐 core/define 的推导）。"""
    prods = list(rule.prods)
    block_start, block_end = "", ""

    def _is_lit_tok(p) -> bool:
        # 与 core/define.py 同款判定：非 @ 且不含组语法字符。
        return (
            isinstance(p, str)
            and not p.startswith("@")
            and not any(ch in p for ch in "()|,*+?")
        )

    if prods and _is_lit_tok(prods[0]):
        block_start = prods[0]
    if prods and _is_lit_tok(prods[-1]):
        block_end = prods[-1]
    elif prods:
        for p in reversed(prods[:-1]):
            if _is_lit_tok(p):
                block_end = p
                break
    bp = list(prods)
    if block_start:
        bp = bp[1:]
    if block_end:
        # 与 core/define.py 同款：剥到 block_end 元素之前（尾组回退场景
        # block_end 不在尾元素）。
        idx = len(bp) - 1
        while idx >= 0 and bp[idx] != block_end:
            idx -= 1
        bp = bp[:idx]
    object.__setattr__(rule, "block_start", block_start)
    object.__setattr__(rule, "block_end", block_end)
    object.__setattr__(rule, "block_prods", bp)


def _replace_in_prods(prods: list, old_str: str, new_str: str) -> bool:
    """逐 production 做子串替换；返回是否有改动。"""
    changed = False
    for i, prod in enumerate(prods):
        if isinstance(prod, str) and old_str in prod:
            prods[i] = prod.replace(old_str, new_str)
            changed = True
    return changed


def inject_replace_rule(
    rules: dict[str, Any],
    replace_config: dict[str, dict[str, str]],
) -> None:
    """replace 路径：按字符串子串替换 production 片段。

    与 inject 路径不同，本路径是**软**的：目标规则缺失只警告跳过（兼容旧
    配置），不做 fail-fast。
    """
    for rule_name, spec in replace_config.items():
        if rule_name not in rules:
            print(f"⚠️ [inject/replace] 规则 {rule_name} 不存在，跳过")
            continue
        rule = rules[rule_name]
        old_str = spec.get("old", "")
        new_str = spec.get("new", "")
        if not old_str:
            continue
        prods = list(rule.prods)
        if _replace_in_prods(prods, old_str, new_str):
            object.__setattr__(rule, "production", tuple(prods))
            if _VERBOSE:
                print(f"  [inject/replace] {rule_name}: {prods}")


def _already_injected(
    feat: dict | None, ext: str, tgt: str, anc_exts: frozenset = frozenset()
) -> bool:
    """树级幂等判据：call@tgt 的任一 choice 祖先含 call@ext 即视为已注入。

    字符串判据（"@Ext|@Tgt" in prod）在多 ext 注入同一 target 时失配：
    注入后 call@tgt 被嵌套 choice 包裹（@TimeDecl|(@RealtimeDecl|...@tgt)），
    中间隔其他 ext 的注入层，"@Ext|@Tgt" 子串不存在 → 重复注入逐 setup
    累积嵌套、serialize 递归爆栈。祖先链判据沿 choice 链收集 call 名，
    只要该 ext 已在 tgt 的注入链上即跳过（幂等），且不影响同一 ext 的
    多 target 传播（test_multiple_targets_propagate：seq 内两个 call@tgt
    各自独立判）。
    """
    if feat is None:
        return False
    typ = feat.get("type")
    if typ == "call":
        return feat.get("name") == tgt and ext in anc_exts
    if typ == "choice":
        alts = feat.get("alternatives", [])
        names = frozenset(
            a.get("name")
            for a in alts
            if a and a.get("type") == "call"
        )
        nxt = anc_exts | names
        return any(_already_injected(a, ext, tgt, nxt) for a in alts)
    if typ in ("repeat", "optional", "plus"):
        return _already_injected(feat.get("elem"), ext, tgt, anc_exts)
    if typ == "seq":
        return any(
            _already_injected(x, ext, tgt, anc_exts)
            for x in feat.get("items", [])
        )
    return False


def _alternatives_of(target_cfg: list | dict) -> list[str]:
    """注入声明的候选列表：`[...]` 直给，或表里取 `alts`。"""
    return target_cfg if isinstance(target_cfg, list) else target_cfg.get("alts", [])


def _inject_into_prod(prod: str, ext_rule_name: str) -> str | None:
    """目标 production → 注入后的 production；已含该 ext → None（幂等跳过）。

    幂等化：目标 production 已含 @ExtRule（重复 setup_grammar 时规则对象被
    `_loaded_dirs` 缓存复用、注入就地改写——无此检查会累积注入层，choice 树
    无限加深最终 serialize 递归爆栈）。

    原字符串语义：顶层 choice → ext 前缀；否则 → 后缀。树层等价：choice →
    插 alternatives 首；非 choice → 包新 choice [ext, feat]。
    """
    if f"@{ext_rule_name}" in prod:
        return None
    feat = analyze_production_features(prod)
    new_feat = insert_choice_candidate(
        feat,
        make_call_feature(ext_rule_name),
        prepend=feat is not None and feat.get("type") == "choice",
    )
    return serialize_production_tree(new_feat)


def _inject_direct(rules: dict[str, Any], ext_rule_name: str, tgt: str) -> None:
    """第一遍：直接注入（目标 production 并入 @ExtRule 候选）。

    fail-fast（ADR-0003）：只支持 production 目标；目标规则缺失直接报错。
    """
    tgt_name, tgt_attr, tgt_idx = _parse_target(tgt)
    if tgt_attr != "production":
        raise GrammarError(
            f"[inject] 仅支持 production 注入目标（{tgt}），got .{tgt_attr}"
        )
    if tgt_name not in rules:
        raise GrammarError(
            f"[inject] 注入目标规则 {tgt_name} 不存在（EXT {ext_rule_name}）"
        )
    target_rule = rules[tgt_name]
    prods = list(target_rule.prods)
    if not prods:
        return
    if tgt_idx >= len(prods):
        prods.append(f"@{ext_rule_name}")
    else:
        new_prod = _inject_into_prod(prods[tgt_idx], ext_rule_name)
        if new_prod is None:
            return
        prods[tgt_idx] = new_prod
    _write_prods(target_rule, prods)


def _propagate_into_prods(
    prods: list, ext_rule_name: str, tgt_name: str, repl: dict
) -> bool:
    """逐 production 做 call[@tgt] → choice[@ext, @tgt] 替换；返回是否有改动。"""
    changed = False
    for i, prod in enumerate(prods):
        if not isinstance(prod, str):
            continue
        feat = analyze_production_features(prod)
        # 幂等化（树级）：call@tgt 的 choice 祖先链已含本 ext → 已注入，跳过
        # ——重复注入会把嵌套 choice 逐 setup 加深，最终 serialize 递归爆栈。
        if _already_injected(feat, ext_rule_name, tgt_name):
            continue
        new_feat = replace_calls(feat, repl)
        if new_feat is not feat:
            prods[i] = serialize_production_tree(new_feat)
            changed = True
    return changed


def _inject_propagate(
    rules: dict[str, Any], ext_rule_name: str, tgt: str, inject_config: Mapping[str, Any]
) -> None:
    """第二遍：传播注入（引用 @Target 的其它规则全树替换）。"""
    tgt_name, _, _ = _parse_target(tgt)
    repl = {
        tgt_name: {
            "type": "choice",
            "alternatives": [
                make_call_feature(ext_rule_name),
                make_call_feature(tgt_name),
            ],
        }
    }
    for other_name, other_rule in rules.items():
        if other_name in inject_config or other_name == tgt_name:
            continue
        other_prods = list(other_rule.prods)
        if not _propagate_into_prods(other_prods, ext_rule_name, tgt_name, repl):
            continue
        _write_prods(other_rule, other_prods)
        if _VERBOSE:
            print(f"  [inject] propagate {other_name}: {other_prods}")


def inject_productions(
    rules: dict[str, Any],
    inject_config: Mapping[str, list[str] | dict],
) -> None:
    """
    结构化两层注入：直接注入 + 传播注入。
    inject_config: { "ExtRule": ["@TargetRule.production[0]"] }

    - 直接注入：目标 production analyze → 树层插入 @ExtRule 候选 → serialize 回写
      （见 `_inject_direct` / `_inject_into_prod`）
    - 传播注入：引用 @Target 的其它规则 analyze → 树层 call[@Target] 替换为
      choice[@Ext, @Target] → serialize 回写（全树，name 精确匹配天然整 token 边界，
      见 `_inject_propagate`）
    - fail-fast（ADR-0003）：target 规则缺失 / 只支持 production / 解析失败 →
      GrammarError，不静默跳过。
    """
    for ext_rule_name, target_cfg in inject_config.items():
        alternatives = _alternatives_of(target_cfg)
        for tgt in alternatives:
            _inject_direct(rules, ext_rule_name, tgt)
        for tgt in alternatives:
            _inject_propagate(rules, ext_rule_name, tgt, inject_config)
