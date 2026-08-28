"""core/global_state.py — 引擎全局状态快照/还原（测试隔离机制，顺序无关）。

背景：语言包引擎存在多处模块级/类级可变单例——GrammarRulesRegister
注册表（只增不重置）、ConfigRegistry 配置（_entries/_loaded/_entries_
source/_sources + 推送进各模块的 _xxx_cfg 模块变量）、plugin_loader 组件
表（_loaded_components/_transform_slots/_PRIMITIVE_ORDER）、pipeline 共享
组件缓存（_PIPELINE_SHARED）、ProjectChecker 共享缓存（_SHARED）。

同一进程内跑多语言/多配置测试时，测试顺序会导致状态残留污染（此前靠各
测试"独立 GrammarRulesRegister() 实例"逐处 workaround 兜底，仍偶发顺序
敏感：批次 5/6 全量跑 intermittently 挂 test_error_category_always_hit
等）。本模块提供统一 snapshot()/restore()：每个测试结束后把全局状态还原
到基线快照，测试顺序无关；CLI/嵌入场景多语言切换后也可调用清理。

设计取舍：
- snapshot 深拷贝轻量状态（注册表 ~2.5ms、配置 ~2ms、模块变量若干），
  每测试还原开销 ~5ms，远优于"每测试重载配置"（~60ms）。
- 按需重建的共享缓存（_PIPELINE_SHARED / ProjectChecker._SHARED）只
  clear 不深拷贝（组件对象重、可能含不可拷贝引用；键控缓存重建成本低）。
- ConfigRegistry._resolve_cache 保留（纯函数缓存：键 = 语言参数，同参数
  结果恒定，不受污染影响）。
"""

from __future__ import annotations

import copy
import sys


def snapshot() -> dict:
    """快照全部引擎全局可变状态。"""
    from core.define import GrammarRulesRegister
    from core.config_registry import ConfigRegistry, _CONFIG_DECLARATIONS
    from core import plugin_loader

    # 配置推送目标模块变量（load_all → _push_loaded_config 写入的 _xxx_cfg）。
    # 只还原 load_all 推过且当前存在的变量；新增注册（declare_cfg）无害，
    # restore 只按快照里的 (module, var) 还原值。
    module_vars: dict[tuple[str, str], object] = {}
    for _key, entries in _CONFIG_DECLARATIONS.items():
        for mod_name, var_name in entries:
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, var_name):
                module_vars[(mod_name, var_name)] = copy.deepcopy(
                    getattr(mod, var_name)
                )

    return {
        "register": copy.deepcopy(GrammarRulesRegister._default_instance),
        "cfg_entries": copy.deepcopy(ConfigRegistry._entries),
        "cfg_loaded": copy.deepcopy(ConfigRegistry._loaded),
        "cfg_entries_source": ConfigRegistry._entries_source,
        "cfg_sources": copy.deepcopy(ConfigRegistry._sources),
        "cfg_resolved": ConfigRegistry._resolved,
        "module_vars": module_vars,
        # 组件表/变换槽含 Python handler（module/函数引用），deepcopy 不可行
        # （TypeError: cannot pickle 'module'）；且组件是 setup_grammar
        # clear+重载的语义——快照只记键集合，restore 移除污染新增键。
        "component_keys": set(plugin_loader._loaded_components),
        "transform_slot_keys": set(plugin_loader._transform_slots),
        "primitive_order": list(plugin_loader._PRIMITIVE_ORDER),
    }


def restore(snap: dict) -> None:
    """把全局状态还原到快照（引用替换；共享缓存清空按需重建）。"""
    from core.define import GrammarRulesRegister
    from core.config_registry import ConfigRegistry
    from core import plugin_loader
    from pipeline import _PIPELINE_SHARED
    from analyzer.checker import ProjectChecker

    GrammarRulesRegister._default_instance = copy.deepcopy(snap["register"])
    ConfigRegistry._entries = copy.deepcopy(snap["cfg_entries"])
    ConfigRegistry._loaded = copy.deepcopy(snap["cfg_loaded"])
    ConfigRegistry._entries_source = snap["cfg_entries_source"]
    ConfigRegistry._sources = copy.deepcopy(snap["cfg_sources"])
    ConfigRegistry._resolved = snap["cfg_resolved"]
    # 注意：快照值不可直接赋给全局（测试会原地 clear/改写全局 → 污染快照
    # 对象本身，后续 restore 还原的是被污染的快照——2026-08-28 实测
    # isolated_registry 的 ConfigRegistry.reset() 清空共享引用即复现）。
    # 每测试 deepcopy 一次 ~5ms，换取快照不可变语义。

    for (mod_name, var_name), value in snap["module_vars"].items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            setattr(mod, var_name, copy.deepcopy(value))

    # 组件表/变换槽：移除基线后新增的键（基线键内容保留——组件按
    # setup_grammar clear+重载语义，测试不改其内部）
    for k in list(plugin_loader._loaded_components):
        if k not in snap["component_keys"]:
            del plugin_loader._loaded_components[k]
    for k in list(plugin_loader._transform_slots):
        if k not in snap["transform_slot_keys"]:
            del plugin_loader._transform_slots[k]
    plugin_loader._PRIMITIVE_ORDER[:] = snap["primitive_order"]

    # 按需重建的键控共享缓存：清空即可（不深拷贝大组件对象）
    _PIPELINE_SHARED.clear()
    ProjectChecker._SHARED.clear()
