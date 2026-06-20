# lexer/lexer_utils.py
import os
import tomllib
from typing import Any
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


def get_token_define(
    token_define: str = FileManager.token_define_file,
) -> dict:
    token_define = FileManager.read_file(token_define)
    token_define_dict: dict = tomllib.loads(token_define)
    return token_define_dict


def get_token_define_from_dir(rules_dir: str) -> dict:
    """从规则目录加载 _token.toml"""
    path = os.path.join(rules_dir, "_token.toml")
    content = FileManager.read_file(path)
    return tomllib.loads(content)


def get_token_define_merged(rules_dir: str) -> dict:
    """两阶段加载：先加载全局 token.toml，再叠加语言特有 _token.toml"""
    base = get_token_define()
    try:
        lang = get_token_define_from_dir(rules_dir)
        return _deep_merge(base, lang)
    except (FileNotFoundError, OSError):
        return base


# 如果使能这个装饰器，则将返回的当前的token值的类型做一次简化，
# 只保留最后一个字段，如 keyword.if -> if
def simplify_output(is_simplify: bool):
    def inner(func):
        def wrapper(*args, **kwargs):
            tokens: list = func(*args, **kwargs)
            for token in tokens:
                token.type = token.type.split(".")[-1] if is_simplify else token.type
            return tokens

        return wrapper

    return inner
