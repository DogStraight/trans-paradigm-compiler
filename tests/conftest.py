"""pytest 共享 fixtures — Lexer + ConfigRegistry。"""

import sys
import os
import pytest

# Windows 控制台/管道编码：DSH 等宿主以 UTF-8 解码子进程输出，而本机活动代码页
# 为 GBK(936) 时 Python stdout 默认用 GBK 编码 → 中文输出（测试 docstring 等）
# 在 UTF-8 解码侧乱码。收集前强制 stdout/stderr 以 UTF-8 输出（Python 3.7+，
# reconfigure 仅影响本进程；测试收集/运行的所有中文输出随之正常）。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue] — hasattr 守卫的真实运行时方法
        sys.stderr.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:  # noqa: BLE001 — 非 tty/受限环境可能拒绝，忽略
        pass

# 将项目根目录加入 sys.path，使各模块可直接导入
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.define import DEFAULT_RULES_DIR
from lexer import Lexer


# ═══════════════════════════════════════════════════════
# ConfigRegistry 初始化：必须先 import 所有模块（触发 declare_cfg），
# 再调用 load_all()（触发 _push_loaded_config 将配置值推入模块变量）。
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def config_loaded() -> None:
    """确保 ConfigRegistry 加载完毕，各模块 _*_cfg 变量已推入。"""
    from core.config_registry import ConfigRegistry

    ConfigRegistry.load_all(
        DEFAULT_RULES_DIR,
        plugins_dir=os.path.join(DEFAULT_RULES_DIR, "plugins"),
    )


# ═══════════════════════════════════════════════════════
# Lexer
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def lexer(config_loaded) -> Lexer:
    """已配置的 Lexer 实例，全局共享。"""
    return Lexer(rules_dir=DEFAULT_RULES_DIR)


# ═══════════════════════════════════════════════════════
# Pratt parser
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def pratt(config_loaded):
    """已配置的 Pratt 解析器模块 + operator_defs + token classifier。"""
    import parser.pratt_parser as pp

    from core.config_registry import ConfigRegistry
    raw = ConfigRegistry._loaded.get("parser.operator_defs", [])
    op_defs = pp.process_operator_data(raw)

    categories = ConfigRegistry._loaded.get("parser.token_categories", {})
    pp.install_token_classifier(categories)

    return pp, op_defs
