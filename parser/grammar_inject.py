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
    if prods and isinstance(prods[0], str) and not prods[0].startswith("@"):
        block_start = prods[0]
    if prods and isinstance(prods[-1], str) and not prods[-1].startswith("@"):
        block_end = prods[-1]
    bp = list(prods)
    if block_start:
        bp = bp[1:]
    if block_end:
        bp = bp[:-1]
    object.__setattr__(rule, "block_start", block_start)
    object.__setattr__(rule, "block_end", block_end)
    object.__setattr__(rule, "block_prods", bp)


def inject_replace_rule(
    rules: dict[str, Any],
    replace_config: dict[str, dict[str, str]],
) -> None:
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
        changed = False
        for i, prod in enumerate(prods):
            if isinstance(prod, str) and old_str in prod:
                prods[i] = prod.replace(old_str, new_str)
                changed = True
        if changed:
            object.__setattr__(rule, "production", tuple(prods))
            if _VERBOSE:
                print(f"  [inject/replace] {rule_name}: {prods}")


def inject_productions(
    rules: dict[str, Any],
    inject_config: Mapping[str, list[str] | dict],
) -> None:
    """
    结构化两层注入：直接注入 + 传播注入。
    inject_config: { "ExtRule": ["@TargetRule.production[0]"] }

    - 直接注入：目标 production analyze → 树层插入 @ExtRule 候选 → serialize 回写
    - 传播注入：引用 @Target 的其它规则 analyze → 树层 call[@Target] 替换为
      choice[@Ext, @Target] → serialize 回写（全树，name 精确匹配天然整 token 边界）
    - fail-fast（ADR-0003）：target 规则缺失 / 只支持 production / 解析失败 →
      GrammarError，不静默跳过。
    """
    for ext_rule_name, target_cfg in inject_config.items():
        alternatives: list[str] = (
            target_cfg if isinstance(target_cfg, list) else target_cfg.get("alts", [])
        )
        ext_call = make_call_feature(ext_rule_name)

        # ── 第一遍：直接注入（目标 production 并入 @ExtRule 候选）──
        for tgt in alternatives:
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
                continue
            if tgt_idx >= len(prods):
                prods.append(f"@{ext_rule_name}")
            else:
                prod = prods[tgt_idx]
                feat = analyze_production_features(prod)
                # 原字符串语义：顶层 choice → ext 前缀；否则 → 后缀。树层等价：
                # choice → 插 alternatives 首；非 choice → 包新 choice [ext, feat]。
                new_feat = insert_choice_candidate(
                    feat,
                    ext_call,
                    prepend=feat is not None and feat.get("type") == "choice",
                )
                prods[tgt_idx] = serialize_production_tree(new_feat)
            _write_prods(target_rule, prods)

        # ── 第二遍：传播注入（引用 @Target 的其它规则全树替换）──
        for tgt in alternatives:
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
                changed = False
                for i, prod in enumerate(other_prods):
                    if not isinstance(prod, str):
                        continue
                    feat = analyze_production_features(prod)
                    new_feat = replace_calls(feat, repl)
                    if new_feat is not feat:
                        other_prods[i] = serialize_production_tree(new_feat)
                        changed = True
                if changed:
                    _write_prods(other_rule, other_prods)
                    if _VERBOSE:
                        print(f"  [inject] propagate {other_name}: {other_prods}")
