# parser/__init__.py
import os
from typing import Dict, Any
from core.define import GrammarRulesRegister, FileManager
from .main_parser import Parser
from .grammar_inject import inject_productions, inject_replace_rule


def setup_grammar(
    rules_dir: str,
    ext_dir: str | None = None,
) -> Dict[str, Any]:
    """加载核心语法 + 增强语法，执行 production injection，返回合并后的规则表。

    封装了标准的三步流程：
      1. 加载核心语法 rules_verilog/
      2. 加载增强语法 rules_verilog_ext/（如有）
      3. 根据 EXT 规则的自声明 [RuleName.inject] 执行注入

    Args:
        rules_dir: 核心语法目录相对路径
        ext_dir: 增强语法目录相对路径（None 表示不加载）
    Returns:
        { rule_name: GrammarRule, ... }
    """
    register = GrammarRulesRegister()
    rules = register.rules_registration(rules_dir)

    if ext_dir:
        ext_dir_full = FileManager.get_full_path(ext_dir)
        if os.path.isdir(ext_dir_full):
            ext_register = GrammarRulesRegister()
            ext_rules = ext_register.rules_registration(ext_dir)
            # 合并到核心规则
            register.rules.update(ext_rules)
            rules.update(ext_rules)

            # 从增强规则的自声明 [RuleName.inject] 构建注入配置
            inject_cfg: dict[str, list[str]] = {}
            replace_cfg: dict[str, dict] = {}
            for rname, rrule in ext_rules.items():
                inj = getattr(rrule, "inject", None)
                if inj and isinstance(inj, dict):
                    targets = inj.get("targets", [])
                    if targets:
                        for t in targets:
                            t_clean = f"@{t}" if not t.startswith("@") else t
                            inject_cfg.setdefault(rname, []).append(t_clean)
                    repl = inj.get("replace", {})
                    if repl:
                        replace_cfg.update(repl)
            if inject_cfg:
                inject_productions(register.rules, inject_cfg)
            if replace_cfg:
                inject_replace_rule(register.rules, replace_cfg)

    return rules


__all__ = ["Parser", "setup_grammar"]
