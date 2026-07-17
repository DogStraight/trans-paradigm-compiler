"""config_map.py — Config declaration and convention mapping.

Reads [config.*] entries from the grammar package's pyv.toml and registers
them with ConfigRegistry. All modules reference config via imported constants.

To add a new engine capability, just add a [config.xxx] entry to the
grammar package's pyv.toml.
"""

import json
import os
import tomllib
from core.config_registry import config


def _find_grammar_pyv_toml() -> str:
    """Locate the grammar package's pyv.toml.

    Follows the two-layer config:
        pyv.config.json → selects grammar package
        grammar/<pkg>/pyv.toml → engine interface config
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Read user config to find which grammar package
    user_config = os.path.join(root, "pyv.config.json")
    rules_dir = "grammar/rules_verilog"  # default
    if os.path.isfile(user_config):
        try:
            with open(user_config, encoding="utf-8") as f:
                cfg = json.load(f)
            rules_dir = cfg.get("grammar", {}).get("rules_dir", rules_dir)
        except (json.JSONDecodeError, KeyError):
            pass  # fallback to default

    meta_path = os.path.join(root, rules_dir, "pyv.toml")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"[config] Grammar package pyv.toml not found: {meta_path}"
        )
    return meta_path


def _flatten_config(table: dict, prefix: str = "") -> list:
    """Recursively flatten nested config table into (dotted_key, spec) pairs.

    [config.lexer]
    token_base = { file = "..." }

    → [("lexer.token_base", {"file": "..."})]
    """
    result = []
    for key, value in table.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "file" not in value:
            result.extend(_flatten_config(value, full_key))
        else:
            result.append((full_key, value))
    return result


def _load_meta_declarations() -> list[tuple]:
    """Read [config.*] declarations from the grammar package pyv.toml."""
    meta_path = _find_grammar_pyv_toml()
    with open(meta_path, encoding="utf-8") as f:
        meta = tomllib.loads(f.read())

    declarations = []
    config_table = meta.get("config", {})
    for config_key, spec in _flatten_config(config_table):
        declarations.append(
            (
                config_key,
                spec.get("file", ""),
                spec.get("section"),
                spec.get("base", "rules"),
                spec.get("required", True),
                spec.get("description", ""),
            )
        )
    return declarations


_DECLARATIONS = _load_meta_declarations()


def install():
    """注册所有配置声明（模块导入时自动执行）。"""
    for name, file, section, base, required, desc in _DECLARATIONS:
        config.declare(
            name,
            file=file,
            section=section,
            base=base,
            required=required,
            description=desc,
        )


# ──────────────────────────────────────────────
# 配置 Key 常量（消除字符串散落）
# ──────────────────────────────────────────────
# 模块通过导入这些常量引用配置，不再使用字符串字面量。
# 如果 TOML 配置结构变化，只需改本文件。

# 词法层
LEXER_TOKEN_BASE = "lexer.token_base"
LEXER_LEXER_BASE = "lexer.lexer_base"
LEXER_TOKEN_LANG = "lexer.token_lang"
LEXER_TOKEN_EXT = "lexer.token_ext"
LEXER_MACRO_CONFIG = "lexer.macro_config"
LEXER_PRE_SCAN = "lexer.pre_scan"

# 解析层
PRATT_OPERATOR_DEFS = "pratt.operator_defs"
PRATT_TOKEN_CATEGORIES = "pratt.token_categories"

# 渲染层
RENDERER_STYLE = "renderer.style"

# 预处理
PREPROCESSOR_EXPAND = "preprocessor.expand"
PREPROCESSOR_DIRECTIVES = "preprocessor.directives"


# 模块导入时自动注册声明
install()
