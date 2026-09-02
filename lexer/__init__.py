"""Lexer 模块 — 词法分析与预扫描。

导出:
    Lexer                    — 主词法分析器
    pre_scan                 — 顶层声明预扫描函数
    load_pre_scan_config     — 加载并编译预扫描 TOML 配置
    get_config_refs          — 扫描本部件配置需求

Doc: docs/language_walkthrough.md（词法层：token 定义驱动）
"""

from core.config_registry import _CONFIG_DECLARATIONS
from . import pre_scan
from .main_lexer import Lexer
from .pre_scan import pre_scan, load_pre_scan_config

__all__ = ["Lexer", "pre_scan", "load_pre_scan_config", "get_config_refs"]


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    prefix = __name__ + "."
    return {
        k: var
        for k, entries in _CONFIG_DECLARATIONS.items()
        for mod, var in entries
        if mod.startswith(prefix)
    }
