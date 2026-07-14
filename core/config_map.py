"""
config_map.py — 配置声明与约定映射

从 grammar/pyv.toml 的 [config.*] 条目读取配置声明，
注册到 ConfigRegistry。所有模块通过导入常量引用配置。

新增引擎能力时，只需在 pyv.toml 追加 [config.xxx] 条目。
"""

import os
import tomllib
from core.config_registry import config


def _flatten_config(table: dict, prefix: str = "") -> list:
    """递归展开嵌套的 config 表为 (dotted_key, spec) 列表。

    [config.lexer]
    token_base = { file = "..." }

    → [("lexer.token_base", {"file": "..."})]
    """
    result = []
    for key, value in table.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "file" not in value:
            # 子表（不含 file 字段 → 继续展开）
            result.extend(_flatten_config(value, full_key))
        else:
            result.append((full_key, value))
    return result


def _load_meta_declarations() -> list[tuple]:
    """从 pyv.toml 的 [config.*] 读取声明列表。"""
    meta_path = os.path.join(os.path.dirname(__file__), "..", "grammar", "pyv.toml")
    with open(meta_path, encoding="utf-8") as f:
        meta = tomllib.loads(f.read())

    declarations = []
    config_table = meta.get("config", {})
    for config_key, spec in _flatten_config(config_table):
        declarations.append((
            config_key,
            spec.get("file", ""),
            spec.get("section"),
            spec.get("base", "rules"),
            spec.get("required", True),
            spec.get("description", ""),
        ))
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
LEXER_TOKEN_BASE      = "lexer.token_base"
LEXER_LEXER_BASE      = "lexer.lexer_base"
LEXER_TOKEN_LANG      = "lexer.token_lang"
LEXER_TOKEN_EXT       = "lexer.token_ext"
LEXER_MACRO_CONFIG    = "lexer.macro_config"
LEXER_PRE_SCAN        = "lexer.pre_scan"

# 解析层
PRATT_OPERATOR_DEFS   = "pratt.operator_defs"
PRATT_TOKEN_CATEGORIES = "pratt.token_categories"

# 渲染层
RENDERER_STYLE        = "renderer.style"

# 预处理
PREPROCESSOR_MACRO_CONFIG = "preprocessor.macro_config"
PREPROCESSOR_EXPAND       = "preprocessor.expand"
PREPROCESSOR_DIRECTIVES   = "preprocessor.directives"

# Linter


# ──────────────────────────────────────────────
# TOML Section 路径常量（消除隐式结构知识）
# ──────────────────────────────────────────────

# bracket 映射（base/token.toml 中的 [bracket] pairs）
BRACKET_PAIRS_PATH = ("bracket", "pairs")

# linter 终止符（base/_linter.toml 中的 [linter] terminators）
LINTER_TERMINATORS_PATH = ("linter", "terminators")


# 模块导入时自动注册声明
install()
