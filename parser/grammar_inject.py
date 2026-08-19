"""Grammar rule injection — production injection, propagation, and replacement.

Supports target addressing syntax: RuleName.production[N]
"""

import json
import re
from collections.abc import Mapping
from typing import Any
from .rule_selector import analyze_production_features


def _has_top_level_choice(prod: str) -> bool:
    feat = analyze_production_features(prod)
    return feat is not None and feat.get("type") == "choice"


def _parse_target(target: str) -> tuple[str, str, int]:
    m = re.match(r"^@?(\w+)(?:\.(\w+))?(?:\[(\d+)\])?$", target)
    if not m:
        return target.lstrip("@"), "production", 0
    return m.group(1), m.group(2) or "production", int(m.group(3)) if m.group(3) else 0


_VERBOSE = False


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
    两层注入：直接注入 + 传播注入。
    inject_config: { "ExtRule": ["@TargetRule.production[0]"] }
    """
    for ext_rule_name, target_cfg in inject_config.items():
        alternatives: list[str] = (
            target_cfg if isinstance(target_cfg, list) else target_cfg.get("alts", [])
        )

        for tgt in alternatives:
            tgt_name, tgt_attr, tgt_idx = _parse_target(tgt)
            if tgt_name not in rules:
                if _VERBOSE:
                    print(f"  [inject] target {tgt_name} not found, skip")
                continue
            target_rule = rules[tgt_name]

            prods = list(target_rule.prods)
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
                other_prods = list(other_rule.prods)
                changed = False
                # 规则引用按完整 token 边界匹配，避免误伤 @StmtOrNull 这类
                # 以目标规则名开头（@Stmt + OrNull）的复合规则名。
                tgt_pattern = re.compile(
                    r"(?<![A-Za-z0-9_])" + re.escape(tgt_ref) + r"(?![A-Za-z0-9_])"
                )
                for i, prod in enumerate(other_prods):
                    if not isinstance(prod, str):
                        continue
                    replacement = f"({target_ref}|{tgt_ref})"
                    if tgt_pattern.search(prod):
                        prod = tgt_pattern.sub(replacement, prod)
                        changed = True
                    other_prods[i] = prod
                if changed:
                    object.__setattr__(other_rule, "production", tuple(other_prods))
                    if _VERBOSE:
                        print(f"  [inject] propagate {other_name}: {other_prods}")
