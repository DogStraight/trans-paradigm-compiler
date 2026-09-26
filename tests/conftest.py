"""pytest 共享 fixtures — Lexer + ConfigRegistry。"""

import random
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
# plugin_loader / pipeline._PIPELINE_SHARED / SharedComponents._CACHE +
# 各模块 _xxx_cfg 配置变量），测试顺序会导致状态残留污染（此前靠各测试
# "独立实例"逐处 workaround，仍偶发顺序敏感）。机制见 core/global_state.py。
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session", autouse=True)
def _global_state_baseline() -> dict:  # pyright: ignore[reportUnusedFunction] — autouse fixture（按名发现）
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
def _restore_global_state(  # pyright: ignore[reportUnusedFunction] — autouse fixture（按名发现）
    _global_state_baseline: dict,
) -> Iterator[None]:
    """每个测试结束后把**测试级**全局状态还原到基线 → 测试顺序无关。

    - 测试级 = 派生缓存 / 注册表新增项 / 共享上下文 / 深度计数器（见
      `core/global_state.py` 的 TRACKED）。
    - 语言安装态（INSTALL_STATE）不在此列：模块级 fixture 构造 Parser 装载
      语言后就合法拥有该状态，逐测试擦除会让同模块后续测试误解析——它由
      `_restore_install_state` 在模块结束时收尾。
    - 还原后立即 assert_clean：把"还原机制自身漏项"当场变红（实测抓到两处：
      keywise 还原不补被删基线键、快照内容依赖导入顺序）。
    """
    yield
    from core.global_state import assert_clean, restore

    restore(_global_state_baseline, scope="test")
    assert_clean(_global_state_baseline)


@pytest.fixture(scope="module", autouse=True)
def _restore_install_state(  # pyright: ignore[reportUnusedFunction] — autouse fixture（按名发现）
    _global_state_baseline: dict,
) -> Iterator[None]:
    """模块结束时还原语言安装态 → 跨模块不串味（模块内由 fixture 自管）。"""
    yield
    from core.global_state import restore

    restore(_global_state_baseline, scope="install")


# ═══════════════════════════════════════════════════════
# 顺序随机化（零依赖）：把"仅在某些文件顺序下出现"的隔离缺口变可复现失败
# ═══════════════════════════════════════════════════════

def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """`TPC_SHUFFLE_SEED=<int>` 时随机化**文件顺序**（未设 = 默认收集序）。

    粒度是文件而不是单个用例：模块级/session 级 fixture 在其作用域内合法拥有
    语言安装态（见 `core/global_state.py` 的 INSTALL_STATE），单用例级乱序会让
    同一模块的作用域被反复拆开重建——那是 fixture 作用域语义问题，不是隔离缺口。
    真正可变的维度是**跨文件顺序**（xdist worker 拿到哪些文件、按什么序跑，
    正是幽灵 flake 的来源），本 hook 抖的就是它。种子固定 → 失败可复现。
    """
    del config  # pytest hook 协议签名（本 hook 只用 items 重排）
    seed = os.environ.get("TPC_SHUFFLE_SEED")
    if not seed:
        return
    by_file: dict[str, list] = {}
    for item in items:
        by_file.setdefault(item.nodeid.split("::", 1)[0], []).append(item)
    order = list(by_file)
    random.Random(int(seed)).shuffle(order)
    items[:] = [item for path in order for item in by_file[path]]
    print(
        f"\n[shuffle] 文件顺序已随机化 seed={seed}"
        f"（复现：TPC_SHUFFLE_SEED={seed}；首文件 {order[0]}）"
    )


@pytest.fixture(scope="session")
def config_loaded(_global_state_baseline: dict) -> None:
    """确保 verilog 配置已加载（session 基线快照已含，兼容既有引用）。"""
    del _global_state_baseline  # fixture 依赖声明（快照由自动 fixture 还原）
    return None


# ═══════════════════════════════════════════════════════
# Lexer
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def lexer(config_loaded) -> Lexer:
    """已配置的 Lexer 实例，全局共享。"""
    del config_loaded  # fixture 依赖声明（配置已由 config_loaded 加载）
    return Lexer(rules_dir=DEFAULT_RULES_DIR)


# ═══════════════════════════════════════════════════════
# Pratt parser
# ═══════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def pratt(config_loaded):
    """已配置的 Pratt 解析器模块 + operator_defs + token classifier。"""
    del config_loaded  # fixture 依赖声明（配置已由 config_loaded 加载）
    import parser.pratt_parser as pp

    from core.config_registry import ConfigRegistry
    raw = ConfigRegistry._loaded.get("parser.operator_defs", [])
    op_defs = pp.process_operator_data(raw)

    categories = ConfigRegistry._loaded.get("parser.token_categories", {})
    pp.install_token_classifier(categories)

    return pp, op_defs
