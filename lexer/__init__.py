# lexer/__init__.py

"""Lexer 模块 — 词法分析与预扫描。

导出:
    Lexer                    — 主词法分析器
    pre_scan                 — 顶层声明预扫描函数
    load_pre_scan_config     — 加载并编译预扫描 TOML 配置
"""

from .main_lexer import Lexer
from .pre_scan import pre_scan, load_pre_scan_config

__all__ = ["Lexer", "pre_scan", "load_pre_scan_config"]
