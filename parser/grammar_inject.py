"""
grammar_inject.py — 语法规则注入工具函数

支持目标寻址语法：RuleName.production[N] / RuleName.end_case
"""

import re
import sys
from typing import Any
from .feature_analyze import analyze_production_features


def _has_top_level_choice(prod: str) -> bool:
    feat = analyze_production_features(prod)
    return feat is not None and feat.get("type") == "choice"


def _parse_target(target: str) -> tuple[str, str, int]:
    m = re.match(r"^@?(\w+)(?:\.(\w+))?(?:\[(\d+)\])?$", target)
    if not m:
        return target.lstrip("@"), "production", 0
    return m.group(1), m.group(2) or "production", int(m.group(3)) if m.group(3) else 0


_VERBOSE = False

def set_verbose(v: bool) -> None:
    global _VERBOSE
    _VERBOSE = v


def inject_alternatives(rule: Any, alternatives: list[str]) -> None:
    prods = list(getattr(rule, "production", []))
    if not prods:
        return
    first_prod = prods[0]
    if isinstance(first_prod, str):
        for alt in alternatives:
            if _has_top_level_choice(first_prod):
                first_prod = f"{alt}|{first_prod}"
            else:
                first_prod += f"|{alt}"
        prods[0] = first_prod
        object.__setattr__(rule, "production", tuple(prods))


def propagate_alternatives(
    rules: dict[str, Any], rule_name: str, alternatives: list[str], skip_names: set[str],
) -> None:
    target_ref = f"@{rule_name}"
    for other_name, other_rule in rules.items():
        if other_name in skip_names:
            continue
        other_prods = list(getattr(other_rule, "production", []))
        changed = False
        for i, prod in enumerate(other_prods):
            if not isinstance(prod, str):
                continue
            for alt in alternatives:
                replacement = f"({target_ref}|{alt})"
                if alt in prod:
                    prod = prod.replace(alt, replacement)
                    changed = True
            other_prods[i] = prod
        if changed:
            object.__setattr__(other_rule, "production", tuple(other_prods))
            if _VERBOSE:
                print(f"  [inject] propagate {other_name}: {other_prods}")


def inject_replace_rule(
    rules: dict[str, Any], replace_config: dict[str, dict[str, str]],
) -> None:
    import json as _json
    for rule_name, spec in replace_config.items():
        if rule_name not in rules:
            print(f"⚠️ [inject/replace] 规则 {rule_name} 不存在，跳过")
            continue
        rule = rules[rule_name]
        old_str = spec.get("old", "")
        new_str = spec.get("new", "")
        if not old_str:
            continue
        ec_prefix = "end_case = "
        if old_str.startswith(ec_prefix):
            current = list(getattr(rule, "end_case", []))
            old_list = _json.loads(old_str[len(ec_prefix):])
            if current == old_list:
                new_list = _json.loads(new_str[len(ec_prefix):])
                object.__setattr__(rule, "end_case", tuple(new_list))
                if _VERBOSE:
                    print(f"  [inject/replace] {rule_name}.end_case -> {new_list}")
            elif _VERBOSE:
                print(f"  [inject/replace] {rule_name}.end_case mismatch: has {current}")
        else:
            prods = list(getattr(rule, "production", []))
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
    rules: dict[str, Any], inject_config: dict[str, list[str] | dict],
) -> None:
    """
    两层注入：直接注入 + 传播注入。
    inject_config: { "ExtRule": ["@TargetRule.production[0]"] }
    """
    for ext_rule_name, target_cfg in inject_config.items():
        alternatives: list[str] = target_cfg if isinstance(target_cfg, list) else target_cfg.get("alts", [])

        for tgt in alternatives:
            tgt_name, tgt_attr, tgt_idx = _parse_target(tgt)
            if tgt_name not in rules:
                if _VERBOSE:
                    print(f"  [inject] target {tgt_name} not found, skip")
                continue
            target_rule = rules[tgt_name]

            if tgt_attr == "end_case":
                current = list(getattr(target_rule, "end_case", []))
                if f"@{ext_rule_name}" not in current:
                    current.append(f"@{ext_rule_name}")
                    object.__setattr__(target_rule, "end_case", tuple(current))
                    if _VERBOSE:
                        print(f"  [inject] {tgt_name}.end_case += {current}")
                continue

            prods = list(getattr(target_rule, "production", []))
            if not prods:
                continue
            if tgt_idx >= len(prods):
                prods.append(f"@{ext_rule_name}")
            else:
                prod = prods[tgt_idx]
                if isinstance(prod, str):
                    if _has_top_level_choice(prod):
                        prod = f"@{ext_rule_name}|{prod}"
                    else:
                        prod += f"|@{ext_rule_name}"
                    prods[tgt_idx] = prod
            object.__setattr__(target_rule, "production", tuple(prods))

        for tgt in alternatives:
            tgt_name, _, _ = _parse_target(tgt)
            tgt_ref = f"@{tgt_name}"
            target_ref = f"@{ext_rule_name}"
            for other_name, other_rule in rules.items():
                if other_name in inject_config or other_name == tgt_name:
                    continue
                other_prods = list(getattr(other_rule, "production", []))
                changed = False
                for i, prod in enumerate(other_prods):
                    if not isinstance(prod, str):
                        continue
                    replacement = f"({target_ref}|{tgt_ref})"
                    if tgt_ref in prod:
                        prod = prod.replace(tgt_ref, replacement)
                        changed = True
                    other_prods[i] = prod
                if changed:
                    object.__setattr__(other_rule, "production", tuple(other_prods))
                    if _VERBOSE:
                        print(f"  [inject] propagate {other_name}: {other_prods}")
