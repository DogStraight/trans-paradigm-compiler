"""parser — 语法解析（递归下降 + Pratt + 规则选择），tokens → AST。

Doc: docs/language_walkthrough.md（语法规则：setup_grammar）
"""
import os
from core.define import GrammarRule, GrammarRulesRegister, FileManager
from .parser_core import Parser
from .grammar_inject import inject_productions, inject_replace_rule


def _apply_ext_injections(
    rules: dict[str, GrammarRule],
    ext_rules: dict[str, GrammarRule],
) -> None:
    """Apply injection configurations from extension rules to the main rule table."""
    inject_config: dict[str, list[str]] = {}
    replace_config: dict[str, dict[str, str]] = {}

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
    register: GrammarRulesRegister | None = None,
    ext_dirs: list[str] | None = None,
) -> dict[str, GrammarRule]:
    """
    Load core grammar + extended grammar, apply production injections,
    and return the merged rule table.

    Args:
        rules_dir: Path to core grammar rules directory (relative).
        ext_dirs: Paths to extended grammar rules directories (optional).
        register: Optional GrammarRulesRegister instance.
                    Defaults to GrammarRulesRegister.get_default().

    Returns:
        { rule_name: GrammarRule, ... }
    """

    if register is None:
        register = GrammarRulesRegister.get_default()
    core_rules = register.rules_registration(rules_dir)

    ext_rules = {}
    for ext_dir in (ext_dirs or []):
        ext_dir_full = FileManager.get_full_path(ext_dir)
        if os.path.isdir(ext_dir_full):
            ext_rules.update(register.rules_registration(ext_dir))

    # 加载组件（含 grammar 文件 + Python handler）——**单语言选择模型**：
    # 只加载当前 rules_dir 语言包的组件，先清空先前语言包的组件状态，
    # 避免多语言组件 grammar 混合进规则表（load_language 切换语言时）。
    try:
        from core.plugin_loader import (
            load_all_components,
            get_component_grammar_files,
            _loaded_components,
        )
        _loaded_components.clear()
        load_all_components(plugins_dir=f"{rules_dir}/plugins")
        for gf_path in get_component_grammar_files():
            comp_rules = register.rules_registration_from_file(gf_path)
            ext_rules.update(comp_rules)
    except ImportError:
        pass

    # Merge core and extension rules
    rules = core_rules.copy()
    rules.update(ext_rules)

    if ext_rules:
        _apply_ext_injections(rules, ext_rules)

    return rules


__all__ = ["Parser", "setup_grammar", "get_config_refs"]


from core.config_registry import _CONFIG_DECLARATIONS


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    prefix = __name__ + "."
    return {k: var for k, entries in _CONFIG_DECLARATIONS.items() for mod, var in entries if mod.startswith(prefix)}
