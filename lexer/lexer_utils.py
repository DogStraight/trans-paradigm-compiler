"""Lexer utilities: TOML config loading and merging.

配置通过 ConfigRegistry 声明式加载，不再内部 try/except 吞错误。
"""

import os
import tomllib
from core.define import FileManager
from core.config_registry import config
from core.config_map import LEXER_TOKEN_BASE, LEXER_LEXER_BASE, LEXER_TOKEN_LANG, LEXER_TOKEN_EXT


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 到 base，override 的值优先"""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_token_define(base_dir: str = "") -> dict:
    """（向后兼容）直接读取 token.toml 文件。新代码应使用 ConfigRegistry。"""
    if not base_dir:
        base_dir = FileManager.token_define_file
    token_content = FileManager.read_file(base_dir)
    return tomllib.loads(token_content)


def get_token_define_merged(rules_dir: str, ext_dirs: list[str] | None = None) -> dict:
    """加载 token 定义：基础定义 + 语言覆盖 + 增强层覆盖。

    替代旧的路径拼接 + try/except 模式。
    """
    base = dict(config.get(LEXER_TOKEN_BASE))
    lexer_cfg = dict(config.get(LEXER_LEXER_BASE))
    base = _deep_merge(base, lexer_cfg)
    try:
        lang = config.get(LEXER_TOKEN_LANG)
        if lang:
            base = _deep_merge(base, lang)
    except KeyError:
        pass
    for ext_dir in (ext_dirs or []):
        try:
            ext_tokens = config.get(LEXER_TOKEN_EXT)
            if ext_tokens:
                base = _deep_merge(base, ext_tokens)
        except KeyError:
            pass
    return base
