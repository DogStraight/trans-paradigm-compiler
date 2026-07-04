"""Lexer utilities: TOML config loading and merging.

配置通过 ConfigRegistry 声明式加载，不再内部 try/except 吞错误。
"""

import os
import tomllib
from core.define import FileManager
from core.config_registry import config


# ========== 配置声明 ==========
config.declare("lexer.token_base",
               file="base/token.toml",
               required=True,
               description="基础词法定义（符号、关键字、括号）")
config.declare("lexer.lexer_base",
               file="base/_lexer.toml",
               required=True,
               description="词法阶段配置（注释解析、token 分类）")
config.declare("lexer.token_lang",
               file="_token.toml",
               required=False,
               description="语言特有词法覆盖")


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


def get_token_define_merged(rules_dir: str) -> dict:
    """两阶段加载：先从 ConfigRegistry 获取，再叠加语言特有覆盖。

    替代旧的路径拼接 + try/except 模式。
    """
    base = dict(config.get("lexer.token_base"))
    lexer_cfg = dict(config.get("lexer.lexer_base"))
    base = _deep_merge(base, lexer_cfg)
    try:
        lang = config.get("lexer.token_lang")
        if lang:
            base = _deep_merge(base, lang)
    except KeyError:
        pass
    return base
