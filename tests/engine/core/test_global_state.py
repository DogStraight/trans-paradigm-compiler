"""tests/engine/core/test_global_state.py — 全局状态快照/还原机制测试。

验证 core/global_state.py 的顺序无关隔离：模拟跨语言污染（注册表注入 c4
规则、ConfigRegistry 切 c4 配置、模块 _xxx_cfg 变量改写、共享缓存写入），
snapshot → restore 后全部还原到基线。配合 conftest 的 autouse fixture
（每个测试后自动还原），测试顺序不再影响结果。
"""

import sys

from core.define import GrammarRulesRegister, DEFAULT_RULES_DIR
from core.config_registry import ConfigRegistry, _CONFIG_DECLARATIONS
from core.global_state import snapshot, restore


def _first_module_var() -> tuple[object, str]:
    """取一个已推送配置的模块变量（任意即可，验证还原）。"""
    for _key, entries in _CONFIG_DECLARATIONS.items():
        for mod_name, var_name in entries:
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, var_name):
                return mod, var_name
    raise AssertionError("无已推送的模块配置变量")


def test_restore_clears_cross_language_rules():
    """污染：全局注册表注入 c4 规则 → 还原后与基线一致。"""
    baseline = snapshot()
    reg = GrammarRulesRegister.get_default()
    before = set(reg.rules)
    assert "grammar/c4" not in reg._loaded_dirs

    reg.rules_registration("grammar/c4")  # 模拟 c4 测试污染全局单例
    assert len(reg.rules) > len(before), "c4 规则未注入（污染模拟失败）"

    restore(baseline)
    # restore 把 _default_instance 换成基线新副本——须重新 get_default()
    # 取新实例（旧引用仍指向污染过的对象，这正是"下一个测试"的真实视角）
    reg = GrammarRulesRegister.get_default()
    assert set(reg.rules) == before
    assert "grammar/c4" not in reg._loaded_dirs


def test_restore_recovers_config_and_entries():
    """污染：ConfigRegistry 切到 c4 语言包 → 还原后回 verilog。"""
    baseline = snapshot()
    v_source = baseline["cfg_entries_source"]

    ConfigRegistry.load_language("grammar/c4")  # 切配置（模拟 c4 测试）
    assert ConfigRegistry._entries_source != v_source, "语言切换未生效"

    restore(baseline)
    assert ConfigRegistry._entries_source == v_source
    assert ConfigRegistry._loaded == baseline["cfg_loaded"]
    assert ConfigRegistry._entries == baseline["cfg_entries"]


def test_restore_restores_module_vars():
    """污染：改写模块 _xxx_cfg 配置变量 → 还原后恢复原值。"""
    mod, var = _first_module_var()
    original = getattr(mod, var)
    baseline = snapshot()

    setattr(mod, var, "POLLUTED")
    assert getattr(mod, var) == "POLLUTED"

    restore(baseline)
    assert getattr(mod, var) == original


def test_restore_clears_shared_caches():
    """共享组件缓存（pipeline/checker）清空还原（按需重建）。"""
    from pipeline import _PIPELINE_SHARED
    from analyzer.checker import ProjectChecker

    baseline = snapshot()
    _PIPELINE_SHARED[("grammar/verilog", ())] = {"x": 1}
    ProjectChecker._SHARED["grammar/verilog"] = {"y": 2}

    restore(baseline)
    assert _PIPELINE_SHARED == {}
    assert ProjectChecker._SHARED == {}


def test_restore_recovers_components():
    """plugin_loader 组件表还原。"""
    from core import plugin_loader

    baseline = snapshot()
    plugin_loader._loaded_components["fake"] = {"capabilities": {"x": lambda: 1}}
    assert "fake" in plugin_loader._loaded_components

    restore(baseline)
    assert "fake" not in plugin_loader._loaded_components


def test_baseline_is_verilog_loaded():
    """基线快照本身是 verilog 已加载态（隔离锚点前提）。"""
    baseline = snapshot()
    assert "ModuleDecl" in baseline["register"].rules
    assert len(baseline["cfg_loaded"]) > 10, (
        f"cfg_loaded 仅 {len(baseline['cfg_loaded'])} 项: "
        f"{list(baseline['cfg_loaded'])[:6]}; "
        f"entries_source={ConfigRegistry._entries_source!r} "
        f"entries={len(ConfigRegistry._entries)}"
    )
    # verilog 规则已注册（conftest session 基线）
    assert "grammar/verilog" in baseline["register"]._loaded_dirs
