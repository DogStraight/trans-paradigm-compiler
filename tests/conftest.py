"""pytest 共享 fixtures — Lexer + ConfigRegistry。"""

import sys
import os
from collections.abc import Iterator

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
# 全局状态隔离（顺序无关）：session 拍基线快照，每个测试后还原。
# 引擎存在多处全局可变单例（GrammarRulesRegister / ConfigRegistry /
# plugin_loader / pipeline._PIPELINE_SHARED / ProjectChecker._SHARED +
# 各模块 _xxx_cfg 配置变量），测试顺序会导致状态残留污染（此前靠各测试
# "独立实例"逐处 workaround，仍偶发顺序敏感）。机制见 core/global_state.py。
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session", autouse=True)
def _global_state_baseline() -> dict:
    """session 基线：加载 verilog 配置并拍全局状态快照（隔离锚点）。"""
    from core.config_registry import ConfigRegistry
    from core.define import GrammarRulesRegister
    from core.global_state import snapshot

    ConfigRegistry.load_all(
        DEFAULT_RULES_DIR,
        plugins_dir=os.path.join(DEFAULT_RULES_DIR, "plugins"),
    )
    GrammarRulesRegister.get_default().rules_registration(DEFAULT_RULES_DIR)
    return snapshot()


@pytest.fixture(autouse=True)
def _restore_global_state(_global_state_baseline: dict) -> Iterator[None]:
    """每个测试结束后把全局状态还原到 verilog 基线 → 测试顺序无关。"""
    yield
    from core.global_state import restore

    restore(_global_state_baseline)


@pytest.fixture(scope="session")
def config_loaded(_global_state_baseline: dict) -> None:
    """确保 verilog 配置已加载（session 基线快照已含，兼容既有引用）。"""
    return None


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
