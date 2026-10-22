"""Lexer 模块 — 词法分析。

导出:
    Lexer                    — 主词法分析器
    get_config_refs          — 扫描本部件配置需求

Doc: docs/language_walkthrough.md（词法层：token 定义驱动）
"""

from core.config_registry import config_refs_for
from .main_lexer import Lexer

__all__ = ["Lexer", "get_config_refs"]


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    return config_refs_for(__name__)
