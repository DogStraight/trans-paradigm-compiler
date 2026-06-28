"""Lexer utilities: TOML config loading and merging."""

import os
import tomllib
from core.define import FileManager


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
    """加载 base/token.toml"""
    if not base_dir:
        base_dir = FileManager.token_define_file
    token_content = FileManager.read_file(base_dir)
    return tomllib.loads(token_content)


def get_token_define_from_dir(rules_dir: str, config_name: str) -> dict:
    """从指定目录加载同名 toml（如 _token.toml）"""
    path = os.path.join(rules_dir, f"{config_name}.toml")
    content = FileManager.read_file(path)
    return tomllib.loads(content)


def get_token_define_merged(rules_dir: str) -> dict:
    """两阶段加载：先加载 base/token.toml + base/_lexer.toml，再叠加语言特有 _token.toml"""
    base_dir = os.path.join(rules_dir, "base")
    base = get_token_define(
        os.path.join(base_dir, "token.toml")
    )
    lexer = get_token_define_from_dir(base_dir, "_lexer")
    base = _deep_merge(base, lexer)
    try:
        lang = get_token_define_from_dir(rules_dir, "_token")
        return _deep_merge(base, lang)
    except (FileNotFoundError, OSError):
        return base

