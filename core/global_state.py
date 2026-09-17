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

全局态登记表（清单即文档，2026-09-14 增）：
引擎的模块级/类级可变容器必须落在六张表之一——`TRACKED`（测试级状态，
每测试还原）、`INSTALL_STATE`（语言安装态，**模块结束**还原）、
`ACCUMULATED`（只增的语言注册面，登记但刻意不还原：还原会与组件模块的
sys.modules 缓存造出"缓存命中 + 注册缺失"不一致态）、`CONTENT_ADDRESSED`
（键 = 输入，同参结果恒定，可跨测试保留）、`CONSTANT`（字面量常量，永不
改写）、`COVERED_ELSEWHERE`（由上方定制逻辑覆盖）。
`tests/policy/test_global_state_coverage.py` 用自动发现扫出引擎包里未登记的
容器并报红——把"记得登记"变成门禁。

两层还原（`restore(scope=...)`）：
- `"test"`（每测试，`tests/conftest.py` 函数级 fixture）：清派生缓存 /
  去掉注册表新增项 / 复位共享上下文与深度计数器。
- `"install"`（每模块，模块级 fixture）：复位语言装载写入的 pratt 安装态
  （parser_core 每次构造 Parser 都会重装，故可还原）。**不能**逐测试复位
  ——模块级 fixture 构造 Parser 装载语言后就合法拥有这些状态，逐测试擦除
  会让同模块后续测试误解析（实测：pratt 合成分类器被 wipe）。
- `"all"`：两者都做（CLI/嵌入场景多语言切换后清理用）。

顺序巡检（把偶发变必现）：`TPC_SHUFFLE_SEED=<int>` 文件级乱序（`tests/conftest.py`
的 `pytest_collection_modifyitems` hook，固定种子 = 可复现）+ `--dist loadfile`
（一个文件固定在同一 worker）。默认收集序只是"某一序"——实测：同一份代码在
不同文件序下曾 5 例失败（本模块 ACCUMULATED 那条边界即由此暴露）。

泄漏检测：`fingerprint()` + `assert_clean()`——每测试**还原后**立即比对基线
指纹（还原机制自身漏项当场红；实测抓到三处：keywise 还原不补被删基线键、
快照内容依赖导入顺序、注册面还原与组件缓存不一致）。

Doc: docs/references.md（测试隔离机制：顺序无关从机制上修复，2026-08-28）
"""

from __future__ import annotations

import copy
import sys

# ── 登记表 1/6：TRACKED——测试级状态（每个测试结束还原）──
# 策略：deepcopy 小数据深拷贝 / ref 不可拷贝引用按引用还原 /
#       clear 纯缓存清空
TRACKED: dict[str, tuple[str, str]] = {
    # 派生缓存（纯函数键控，清空即安全）
    "parser._production._prod_feat_cache": ("clear", "生产式特征缓存（键 = 规则名::production）"),
    "renderer.doc._LAYOUT_CACHE": ("clear", "per-layout 记忆化（layout 入口亦清，双保险）"),
    # 跨插件共享上下文（每次运行重设 rules/mapping_cfg）
    "transform.engine.AstTransformer._shared_ctx": ("clear", "插件共享上下文（rules/mapping_cfg）"),
    # 递归深度计数器：异常路径漏减会残留 → 后续测试误判"超深"（典型幽灵来源）
    "linter.checkers.expression.ExpressionChecker._DEPTH": ("deepcopy", "表达式检查递归深度计数"),
    # 共享组件缓存
    "pipeline._PIPELINE_SHARED": ("clear", "管线共享组件（键 = (rules_dir, ext_dirs)）"),
    "analyzer.checker.ProjectChecker._SHARED": ("clear", "checker 共享组件（按 rules_dir 键控）"),
}

# ── 登记表 2/6：INSTALL_STATE——语言安装态（模块结束还原）──
# 由语言装载/Parser 构造（parser_core）按语言写入。**不在**测试级表内：模块级
# fixture（构造 Parser 装载语言）在自己模块内合法拥有它们，测试级还原会把它擦掉
# （实测：pratt 合成分类器被 wipe → 同模块后续测试误解析）。
# 可还原的前提：**下一次解析入口会幂等重装**（parser_core 每次构造 Parser 都调
# install_*）——所以模块结束还原 = 跨模块不串味，模块内由 fixture 自管。
INSTALL_STATE: dict[str, tuple[str, str]] = {
    "parser.pratt_parser._token_checks": ("deepcopy", "token 类别判定表（install_token_classifier）"),
    "parser.pratt_parser._bit_width_literal_parser": ("ref", "位宽字面量解析器（按语言安装）"),
    "parser.pratt_parser._bool_true_type": ("ref", "bool 真值类型（按语言安装）"),
    "parser.pratt_parser._atom_name_map": ("deepcopy", "原子 token→规则名映射（按语言安装）"),
    # 语言作用域（当前语言装载了哪些组件）：插件应用按它过滤，
    # **模块级**还原——逐测试清掉会让同模块后续用例的 transform 空转（实测）。
    "core.plugin_loader._active_components": ("deepcopy", "当前语言的组件作用域（插件过滤用）"),
}

# ── 登记表 3/6：ACCUMULATED——只增的语言注册面（登记但**刻意不还原**）──
# 写入者是**模块导入副作用**（插件文件/原语模块 import 期注册），而
# plugin_loader 缓存组件模块（sys.modules 命中即不重 exec）——还原注册面会造出
# 不一致态：缓存命中 → 不重注册 → 注册面空。2026-09-14 实测：c4 模块结束还原
# 后，同 worker 下一个 c4 文件装载组件命中缓存 → AsmGenPlugin 不再注册 →
# transform 退化为 Program（默认序 + `--dist loadfile` 下 5 例失败）。
# 累积**本身不安全**（已实测证伪早先的"跨语言多出来的条目不被引用"）：
# `AstTransformer` 会实例化并执行登记的全部插件，别的语言的插件会参与本语言
# 管线。安全来自**应用侧按语言作用域过滤**（`transform.engine.
# active_plugin_classes()`：引擎插件 + `core.plugin_loader._active_components`），
# 而不是靠注册名限定——新增插件接入点时必须同样接这个过滤。
ACCUMULATED: dict[str, str] = {
    "transform.engine._plugin_registry": "插件注册表（应用侧按语言作用域过滤，见 active_plugin_classes）",
    "transform.engine._plugin_origins": "插件来源组件表（与注册表平行，同上）",
    "transform.engine._plugin_index": "限定名→插件类索引（按名解析，不参与执行）",
    "transform.engine._plugin_contracts": "插件契约表（同上，校验用）",
    "transform.engine._plugin_shapes": "插件产物形状声明（同上，校验用）",
    "renderer.primitives.registry._PRIMITIVE_REGISTRY": "渲染原语注册表（原语模块 import 期注册）",
    "analyzer.primitives.registry._primitives": "分析原语注册表（原语模块 import 期注册）",
    "analyzer.primitives._symbol._capture_hooks": "符号捕获钩子表（同上）",
    "preprocessor.primitives.registry._registry": "指令处理原语注册表（同上）",
    "transform.primitives.registry._registry": "变换原语注册表（同上）",
}

# ── 登记表 4/6：CONTENT_ADDRESSED——键 = 输入，同参结果恒定，可保留 ──
CONTENT_ADDRESSED: dict[str, str] = {
    "core.config_registry.ConfigRegistry._resolve_cache": "键 = 语言参数元组（纯函数缓存）",
    "preprocessor.macro_shape._PARSE_CACHE": "键 = 宏形态 shape 生产式字符串（纯函数缓存）",
    "lexer.comment_syntax._CACHE": "键 = rules_dir（注释形态：行注释起始/成对定界符）",
    "analyzer.checks._HANDLER_CACHE": "键 = 插件目录（handler 模块跨次复用）",
    "lexer.pre_scan._CACHE": "键 = rules_dir",
}

# ── 登记表 5/6：COVERED_ELSEWHERE——由 snapshot/restore 定制逻辑覆盖 ──
COVERED_ELSEWHERE: dict[str, str] = {
    "core.define.GrammarRulesRegister._default_instance": "snapshot 深拷贝注册表实例",
    "core.config_registry.ConfigRegistry._entries": "snapshot 深拷贝",
    "core.config_registry.ConfigRegistry._loaded": "snapshot 深拷贝",
    "core.config_registry.ConfigRegistry._sources": "snapshot 深拷贝",
    "core.check_registry._CHECK_RULES": "快照键集合（只去新增）",
    "core.check_registry._USER_CONFIG_CACHE": "快照键集合（只去新增）",
    "core.plugin_loader._loaded_components": "快照键集合（只去新增）",
    "core.plugin_loader._transform_slots": "快照键集合（只去新增）",
    "core.plugin_loader._PRIMITIVE_ORDER": "快照列表还原",
    "core.config_registry._CONFIG_DECLARATIONS": "declare_cfg 声明表（snapshot 遍历它覆盖 module_vars；只增）",
}

# ── 登记表 6/6：CONSTANT——字面量常量，永不改写（若改写即缺陷）──
CONSTANT: dict[str, str] = {
    "core.check_registry._SEVERITIES": "严重度字面量集合",
    "preprocessor.macro_policy.DEFAULT_PLAN": "引擎默认宏处置方案（未声明策略能力时用）",
    "core.config_registry._DECL_FIELDS": "声明字段名字面量",
    "core.config_registry._DECLARATIONS": "import 期加载的声明规格表（只读）",
    "core._user_config._CONFIG_CANDIDATES": "配置文件候选路径",
    "core.define.DEFAULT_EXT_DIRS": "默认扩展目录（import 期从 tpc.toml 派生）",
    "core.define._tpc_meta": "默认语言包 meta（import 期加载，只读派生 DEFAULT_*）",
    "core.define.GrammarRule._BOOL_FIELDS": "规则字段 schema 字面量",
    "core.define.GrammarRule._LIST_FIELDS": "规则字段 schema 字面量",
    "core.define.GrammarRule._STAGE_FIELDS": "规则字段 schema 字面量",
    "core.define.GrammarRule._TOP_LEVEL_FIELDS": "规则字段 schema 字面量",
    "core.define.GrammarRule._KNOWN_FIELDS": "规则字段 schema 字面量",
    "analyzer.report_html._SEVERITY_META": "严重度展示元数据字面量",
    "lexer.main_lexer.Lexer.token_define": "类级默认模板（实例构造即重绑 self.token_define）",
    "lexer.number_gen._CHAR_CATEGORY": "字符类别字面量表",
    "linter.checkers.expression.ExpressionChecker._MAX_DEPTH": "最大递归深度常量",
    "main._CMD_DEFAULTS": "CLI 子命令默认值",
    "parser._production._DISPATCH": "节点分发表字面量",
    "parser.rule_selector.SEPARATOR_HANDLERS": "production 分隔符处理器表（模块级字面量）",
    "parser.rule_selector.SUFFIX_MAP": "后缀→节点类型表字面量",
    "pipeline.report_html._KIND_CSS": "报告款式字面量",
    "pipeline.schedule.BUILTIN_PASSES": "内置 pass 名字面量",
    "pipeline.schedule.DEFAULT_SCHEDULE_ENTRIES": "默认调度序字面量",
    "pipeline.schedule._BUILTIN_UNIT_CONTRACTS": "内置单元契约字面量",
    "transform.normalizer.EXTRACT_PREFIXES": "抽取前缀字面量",
}

_ENGINE_PACKAGES = (
    "core", "lexer", "parser", "linter", "preprocessor",
    "analyzer", "transform", "renderer", "pipeline",
)
_REGISTRY_TABLES = (
    TRACKED, INSTALL_STATE, ACCUMULATED, CONTENT_ADDRESSED, COVERED_ELSEWHERE, CONSTANT
)


def _split_target(name: str) -> tuple[object, str]:
    """`pkg.mod[.Class].attr` → (宿主对象, 最后一段属性名)。

    从最长的可导入模块前缀开始尝试（类属性如 `ProjectChecker._SHARED` 走
    `mod.Class.attr` 形态）；前缀未导入时**按需导入**（基线快照可能早于
    懒加载模块的导入时点，如 linter.checkers.expression）。
    """
    import importlib

    parts = name.split(".")
    for split in range(len(parts) - 1, 0, -1):
        try:
            mod = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        obj: object = mod
        for attr in parts[split:-1]:
            obj = getattr(obj, attr)
        return obj, parts[-1]
    raise LookupError(f"无法解析全局态条目：{name}")


def discover_mutable_globals() -> list[str]:
    """扫描引擎包的模块级/类级可变容器（dict/list/set/bytearray）→ 条目名。

    范围 = `_ENGINE_PACKAGES` + main（语言包插件目录的内容数据常量较多，
    且插件表已由 plugin_loader 登记表覆盖）。`core.global_state` 自身
    排除（登记表本体）。

    别名去重：同一对象被多个模块 `import` 绑定时（如 `_CONFIG_DECLARATIONS`
    在 core/lexer/parser 各处可见），按 `_ENGINE_PACKAGES` 顺序取首个出现的
    **归属名**；类级容器统一用 `类.__module__ + 类.__qualname__` 命名
    （不受 `config = ConfigRegistry` 这类别名影响）。
    """
    import importlib
    import pkgutil

    names: list[str] = []
    for pkg in _ENGINE_PACKAGES:
        try:
            mod = importlib.import_module(pkg)
        except Exception:  # noqa: BLE001 — 按需导入失败不阻塞扫描
            continue
        path = getattr(mod, "__path__", None)
        if path is not None:
            # 子模块先于包模块：别名的"归属名"落到定义处（如
            # `_CONFIG_DECLARATIONS` → core.config_registry，而非 lexer）
            names.extend(info.name for info in pkgutil.walk_packages(path, pkg + "."))
        names.append(pkg)
    names.append("main")

    found: dict[int, str] = {}  # 容器 id → 条目名（首见归属名）
    for name in names:
        if name == "core.global_state":
            continue
        try:
            mod = importlib.import_module(name)
        except Exception:  # noqa: BLE001 — 可选依赖缺失时跳过该模块
            continue
        for attr, value in vars(mod).items():
            if attr.startswith("__"):
                continue
            if isinstance(value, (dict, list, set, bytearray)):
                found.setdefault(id(value), f"{name}.{attr}")
            elif isinstance(value, type) and value.__module__ == name:
                owner = f"{value.__module__}.{value.__qualname__}"
                for c_attr, c_val in vars(value).items():
                    if c_attr.startswith("__"):
                        continue
                    if isinstance(c_val, (dict, list, set, bytearray)):
                        found.setdefault(id(c_val), f"{owner}.{c_attr}")
    return sorted(found.values())


def _warm_imports() -> None:
    """预先解析全部登记条目（触发按需导入）。

    模块导入有注册副作用（如分析原语的 import 期注册）——不预热则快照内容
    取决于 `_split_target` 触发导入的顺序，快照与还原读到不同集合（实测：
    `_primitives` 快照 4 项、还原时现场 5 项 → 还原反把基线项删掉）。
    """
    for table in _REGISTRY_TABLES:
        for name in table:
            try:
                _split_target(name)
            except (LookupError, AttributeError):
                pass


def _registered_ids() -> dict[int, str]:
    """登记表中各条目"指向对象 id → 条目名"（用于别名识别）。"""
    ids: dict[int, str] = {}
    for table in _REGISTRY_TABLES:
        for name in table:
            try:
                owner, attr = _split_target(name)
            except (LookupError, AttributeError):
                continue
            ids[id(getattr(owner, attr, None))] = name
    return ids


def _declared_cfg_pairs() -> set[tuple[str, str]]:
    """`declare_cfg` 登记的 (模块名, 变量名) 对（module_vars 快照已覆盖它们）。"""
    from core.config_registry import _CONFIG_DECLARATIONS

    return {
        (mod_name, var_name)
        for entries in _CONFIG_DECLARATIONS.values()
        for mod_name, var_name in entries
    }


def _auto_covered_reason(name: str, registered: dict[int, str]) -> str | None:
    """规则化覆盖（比逐条登记不易漂）：返回理由，None = 必须显式登记。"""
    try:
        owner, attr = _split_target(name)
    except (LookupError, AttributeError):
        return None
    alias_of = registered.get(id(getattr(owner, attr, None)))
    if alias_of:
        return f"别名（与 {alias_of} 同对象）"
    mod_name, _, _ = name.rpartition(".")
    for pair_mod, pair_var in _declared_cfg_pairs():
        if pair_mod == mod_name and name.endswith("." + pair_var):
            return "declare_cfg 推送值（module_vars 快照覆盖）"
    return None


def unregistered_globals() -> list[str]:
    """发现了但未登记（且不属规则化覆盖）的全局态——覆盖门禁的报红集。"""
    registered = {n for table in _REGISTRY_TABLES for n in table}
    ids = _registered_ids()
    return [
        n
        for n in discover_mutable_globals()
        if n not in registered and _auto_covered_reason(n, ids) is None
    ]


def _value_digest(value: object) -> str:
    """单个值的廉价摘要（标量取 repr，容器取类型#长度，对象取类型名）。

    刻意**不含 id()**：deepcopy 策略还原出的对象每次都是新实例，按 id 比会
    把小 dict 的合法还原误判为泄漏。
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return repr(value)[:48]
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return f"{type(value).__name__}#{len(value)}"
    return type(value).__name__


def _signature(value: object) -> tuple:
    """全局态条目的廉价指纹。

    小 dict（≤32 键）连**键值摘要**一起算——否则 `_DEPTH={"n": 0}` 这类
    "只改值不改键"的泄漏抓不到；大 dict 退回键集合 + 长度（成本优先）。
    """
    if isinstance(value, dict):
        keys = sorted(map(str, value.keys()))
        if len(value) <= 32:
            pairs = tuple(sorted((str(k), _value_digest(v)) for k, v in value.items()))
            return ("dict", len(value), pairs)
        return ("dict", len(value), tuple(keys[:8]), tuple(keys[-8:]))
    if isinstance(value, (list, tuple)):
        return (
            "seq",
            len(value),
            tuple(_value_digest(x) for x in value[:4]),
            tuple(_value_digest(x) for x in value[-4:]),
        )
    if isinstance(value, set):
        return ("set", len(value), tuple(sorted(map(str, value))[:8]))
    return ("ref", type(value).__name__)


def fingerprint() -> dict[str, tuple]:
    """TRACKED 各条目的指纹（用于测试开始前的基线比对）。"""
    _warm_imports()
    out: dict[str, tuple] = {}
    for name in TRACKED:
        owner, attr = _split_target(name)
        out[name] = _signature(getattr(owner, attr))
    return out


def assert_clean(baseline: dict) -> None:
    """断言当前全局态指纹 == 基线（每个测试开始前调：泄漏当场变红）。"""
    want = baseline.get("tracked_fingerprint") or {}
    now = fingerprint()
    changed = [
        n for n in sorted(set(want) | set(now)) if want.get(n) != now.get(n)
    ]
    if changed:
        detail = "\n".join(
            f"  {n}\n    基线: {want.get(n)}\n    当前: {now.get(n)}"
            for n in changed
        )
        raise AssertionError(
            "全局态未回到基线（上一测试泄漏，登记表 TRACKED 条目）：\n" + detail
        )


def snapshot() -> dict:
    """快照全部引擎全局可变状态。"""
    from core.define import GrammarRulesRegister
    from core.config_registry import ConfigRegistry, _CONFIG_DECLARATIONS
    from core import plugin_loader

    # 配置推送目标模块变量（load_all → _push_loaded_config 写入的 _xxx_cfg）。
    # 只还原 load_all 推过且当前存在的变量；新增注册（declare_cfg）无害，
    # restore 只按快照里的 (module, var) 还原值。
    module_vars: dict[tuple[str, str], object] = {}
    for _, entries in _CONFIG_DECLARATIONS.items():
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
        # 声明式检查规则表（core/check_registry._CHECK_RULES）：纯数据，
        # 快照键集合即可——restore 移除污染新增键（跨语言测试残留）。
        "check_rule_keys": set(
            __import__("core.check_registry", fromlist=["_CHECK_RULES"])._CHECK_RULES
        ),
        # 用户检查配置缓存（_USER_CONFIG_CACHE）：按配置文件路径键控，
        # 测试用 $TPC_CONFIG 注入后残留会串——快照键集合，restore 清空。
        "check_user_cfg_keys": set(
            __import__("core.check_registry", fromlist=["_USER_CONFIG_CACHE"])._USER_CONFIG_CACHE
        ),
        # 登记表 TRACKED（测试级）/ INSTALL_STATE（安装态）的通用快照
        # （按策略：deepcopy / ref / clear 不存值 / keywise 存键值 / prefix 存序列）
        # + 测试级基线指纹（每测试还原后比对用）。
        "tracked": _snapshot_tracked(TRACKED),
        "install": _snapshot_tracked(INSTALL_STATE),
        "tracked_fingerprint": fingerprint(),
    }


def _snapshot_tracked(table: dict[str, tuple[str, str]]) -> dict[str, object]:
    """按策略快照表中各条目。"""
    _warm_imports()
    saved: dict[str, object] = {}
    for name, (strategy, _) in table.items():
        owner, attr = _split_target(name)
        value = getattr(owner, attr)
        if strategy == "deepcopy":
            saved[name] = copy.deepcopy(value)
        elif strategy == "ref":
            saved[name] = value
        else:  # clear：不存值（还原即清空）
            saved[name] = None
    return saved


def _restore_tracked(snap: dict, table: dict[str, tuple[str, str]], slot: str) -> None:
    """按策略还原表中各条目（`slot` = 快照内键："tracked" / "install"）。"""
    _warm_imports()
    for name, (strategy, _) in table.items():
        owner, attr = _split_target(name)
        saved = snap[slot][name]
        current = getattr(owner, attr)
        if strategy == "deepcopy":
            setattr(owner, attr, copy.deepcopy(saved))
        elif strategy == "ref":
            setattr(owner, attr, saved)
        elif strategy == "clear":
            if isinstance(current, dict):
                current.clear()
            elif isinstance(current, list):
                del current[:]
            elif isinstance(current, set):
                current.clear()


def restore(snap: dict, scope: str = "all") -> None:
    """把全局状态还原到快照（引用替换；共享缓存清空按需重建）。

    scope："all" 全部 / "test" 仅测试级 TRACKED / "install" 仅安装态。
    测试级 restored 每测试调用；安装态由**模块级** fixture 在模块结束时调用
    （模块内的语言装载由该模块自己的 fixture 拥有，不能被逐测试擦除）。
    """
    from core.define import GrammarRulesRegister
    from core.config_registry import ConfigRegistry
    from core import plugin_loader

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

    # 声明式检查规则表：移除基线后新增的键（规则表是静态数据，基线键
    # 内容保留——测试不改其内部，只防跨语言残留）
    _check_reg = __import__("core.check_registry", fromlist=["_CHECK_RULES"])
    for k in list(_check_reg._CHECK_RULES):
        if k not in snap["check_rule_keys"]:
            del _check_reg._CHECK_RULES[k]
    # 用户检查配置缓存：清空基线后新增的键（防 $TPC_CONFIG 注入残留）
    for k in list(_check_reg._USER_CONFIG_CACHE):
        if k not in snap["check_user_cfg_keys"]:
            del _check_reg._USER_CONFIG_CACHE[k]

    # 登记表 TRACKED：按策略通用还原（测试级状态；语言安装态 INSTALL_STATE
    # 不在此列——模块级 fixture 拥有，由 restore(scope="install") 收尾）
    if scope in ("all", "test"):
        _restore_tracked(snap, TRACKED, "tracked")
    if scope in ("all", "install"):
        _restore_tracked(snap, INSTALL_STATE, "install")
