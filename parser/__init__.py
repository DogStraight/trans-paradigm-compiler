# parser/__init__.py
import os
from typing import Dict, Optional
from core.define import GrammarRule, GrammarRulesRegister, FileManager
from .main_parser import Parser
from .grammar_inject import inject_productions, inject_replace_rule


def _apply_ext_injections(
    rules: Dict[str, GrammarRule],
    ext_rules: Dict[str, GrammarRule],
) -> None:
    """Apply injection configurations from extension rules to the main rule table."""
    inject_config: Dict[str, list] = {}
    replace_config: Dict[str, Dict[str, str]] = {}

    for r_name, r_rule in ext_rules.items():
        inj = getattr(r_rule, "inject", None)
        if inj and isinstance(inj, dict):
            targets = inj.get("targets", [])
            if targets:
                for t in targets:
                    inject_config.setdefault(r_name, []).append(t)
            repl = inj.get("replace", {})
            if repl:
                replace_config.update(repl)

    if inject_config:
        inject_productions(rules, inject_config)
    if replace_config:
        inject_replace_rule(rules, replace_config)


def setup_grammar(
    rules_dir: str,
    register: Optional[GrammarRulesRegister] = None,
    ext_dir: Optional[str] = None,
) -> Dict[str, GrammarRule]:
    """
    Load core grammar + extended grammar, apply production injections,
    and return the merged rule table.

    Args:
        rules_dir: Path to core grammar rules directory (relative).
        ext_dir: Path to extended grammar rules directory (optional).
        register: Optional GrammarRulesRegister instance.
                  Defaults to GrammarRulesRegister.get_default().

    Returns:
        { rule_name: GrammarRule, ... }
    """

    if register is None:
        register = GrammarRulesRegister.get_default()
    core_rules = register.rules_registration(rules_dir)

    ext_rules = {}
    if ext_dir:
        ext_dir_full = FileManager.get_full_path(ext_dir)
        if os.path.isdir(ext_dir_full):
            ext_rules = register.rules_registration(ext_dir)

    # Merge core and extension rules
    rules = core_rules.copy()
    rules.update(ext_rules)

    if ext_rules:
        _apply_ext_injections(rules, ext_rules)

    return rules


__all__ = ["Parser", "setup_grammar"]
