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
        if not inj or not isinstance(inj, dict):
            continue
        _collect_inject_targets(inject_config, r_name, inj.get("targets", []))
        _merge_replace_config(replace_config, inj.get("replace", {}))

    if inject_config:
        inject_productions(rules, inject_config)
    if replace_config:
        inject_replace_rule(rules, replace_config)


def _collect_inject_targets(
    config: dict[str, list[str]], rule_name: str, targets
) -> None:
    """登记该扩展规则要注入的目标规则名（未声明 targets 时不登记）。"""
    if not targets:
        return
    for t in targets:
        config.setdefault(rule_name, []).append(t)


def _merge_replace_config(config: dict[str, dict[str, str]], repl) -> None:
    """合并该扩展规则的替换配置（未声明 replace 时不合并）。"""
    if repl:
        config.update(repl)


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
    # 语言作用域：同一注册器不跨语言累积（切换语言 = 重建规则表）。
    # 不这样做时后一语言的规则表会混入前一语言规则，且顺序靠前——
    # RuleSelector.get_block_rule 取"第一个匿名块规则"，根规则会被夺走
    # （实测：c4 → verilog 后 verilog 源码按 c4 的 Program 解析，输出为空）。
    register.begin_language(rules_dir)
    core_rules = register.rules_registration(rules_dir)

    ext_rules = {}
    for ext_dir in (ext_dirs or []):
        ext_dir_full = FileManager.get_full_path(ext_dir)
        if os.path.isdir(ext_dir_full):
            ext_rules.update(register.rules_registration(ext_dir))

    # 加载组件（含 grammar 文件 + Python handler）——**单语言选择模型**：
    # 只加载当前 rules_dir 语言包的组件，先清空先前语言包的组件状态，
    # 避免多语言组件 grammar 混合进规则表（load_language 切换语言时）。
    # **不吞异常**（fail-fast，core/config_lifecycle.md）：此前这一段包在
    # `except ImportError: pass` 里——装载期任何 ImportError（插件模块循环导入/
    # 部分初始化等）会被静默吞掉，语言作用域停在上一语言（实测症状：
    # 切到 verilog 后 c4 的插件仍在作用域内、组件规则缺失），与"配置加载
    # fail-fast、不静默降级"硬约束冲突。
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

    # Merge core and extension rules
    rules = core_rules.copy()
    rules.update(ext_rules)

    if ext_rules:
        _apply_ext_injections(rules, ext_rules)

    return rules


__all__ = ["Parser", "setup_grammar", "get_config_refs"]


from core.config_registry import config_refs_for


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    return config_refs_for(__name__)
