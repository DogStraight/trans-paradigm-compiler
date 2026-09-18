"""plugin_loader.py — Plugin loading and management.

A component is a self-contained unit of grammar rules + analyzer primitives
+ transform slots, located in grammar/<lang>/plugins/<name>/.
Doc: core/component_protocol.md（插件发现/加载）
"""

import importlib.util
import os
import sys
from typing import Any, Callable

from core._protocol import META_NAME, META_REQUIRES, SLOT_CTX_SELF

def _get_component_dir(plugins_dir: str = "") -> str:
    """Resolve component directory.

    plugins_dir 非空时用指定语言包的 plugins/（单语言选择——跟随
    load_language 选中的语言包）；否则用默认包 DEFAULT_RULES_DIR/plugins。
    """
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if plugins_dir:
            abs_dir = (
                plugins_dir
                if os.path.isabs(plugins_dir)
                else os.path.join(root, plugins_dir)
            )
            return abs_dir if os.path.isdir(abs_dir) else ""
        from core.define import DEFAULT_RULES_DIR
        pdir = os.path.join(root, DEFAULT_RULES_DIR, "plugins")
        if os.path.isdir(pdir):
            return pdir
    except OSError:
        # 仅容忍文件系统级异常；import/配置异常（如 ConfigError）应冒泡而非静默
        return ""
    return ""

_loaded_components: dict[str, dict[str, Any]] = {}
_transform_slots: dict[str, Callable] = {}
_PRIMITIVE_ORDER: list[str] = []
# 语言作用域是否已建立（`load_all_components` 跑过）：区分"当前语言无组件"与
# "从未装载过任何语言"——插件按作用域过滤时，前者应过滤到空，后者不过滤
# （纯单测直接 import 插件模块的场景）。
_components_initialized: bool = False
# 当前语言作用域的组件集（**装载时固化**，不读实时 `_loaded_components`）：
# 后者会被测试隔离的测试级还原改（按基线删新增键），拿它当作用域会把本语言的
# 插件也滤掉（实测：c4 模块内第二个用例开始 transform 空转）。
_active_components: set[str] = set()


def discover_components(plugins_dir: str = "") -> list[dict[str, Any]]:
    """递归扫描 plugins/ 目录树，收集所有含 tpc.toml 的组件目录。

    聚类目录支持（用户自定义分类，引擎不规定枚举值）：plugins/ 下任意
    深度子目录均可作为分类容器（如 plugins/checks/name_check），任何含
    tpc.toml 的目录都是一个组件；不含 tpc.toml 的目录只是分类容器被
    跳过。组件名 = tpc.toml 所在目录的 basename（与既有引用兼容：依赖/
    配置/启用列表均按组件名引用）。重名组件（不同分类下同名）→ fail-fast
    （ADR-0003）。
    """
    comp_dir = _get_component_dir(plugins_dir)
    if not comp_dir or not os.path.isdir(comp_dir):
        return []
    result = []
    seen_names: dict[str, str] = {}
    for root, dirs, files in os.walk(comp_dir):
        # 跳过私有目录（_ 前缀，如 __pycache__）
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        if "tpc.toml" not in files:
            continue
        cdir = root
        toml_path = os.path.join(cdir, "tpc.toml")
        name = os.path.basename(cdir)
        if name in seen_names:
            raise ValueError(
                f"Component name conflict: '{name}' in {seen_names[name]} "
                f"and {cdir}"
            )
        seen_names[name] = cdir
        meta = _parse_component_toml(toml_path)
        if meta:
            meta["_dir"] = cdir
            result.append(meta)
    result.sort(key=lambda m: m[META_NAME])
    return result


def _parse_component_toml(path: str) -> dict[str, Any] | None:
    """Parse plugin tpc.toml's [grammar]/[analyzer]/[transform]/[pipeline]/[capabilities]/[render]."""
    import tomllib

    with open(path, "rb") as f:
        raw = tomllib.load(f)
    # 组件判定：有 [grammar] files，或有 [transform] handlers（如 c4 的
    # asm_gen——无语法规则文件，只有代码生成插件），或有 [analyzer] handlers
    # （纯语义检查插件，如 semantic_check——无语法规则，只有检查原语），
    # 或有 [analyzer] postpasses（纯 post-pass 联动检查插件，如 inst_check），
    # 或有 [pipeline] 段（自定义 pass / schedule 声明，ADR-0007），
    # 或有 [capabilities] 段（能力声明，P2.5 插件回调能力化——如 formatter
    # 纯能力插件：无语法/变换/分析声明，只向引擎暴露能力入口），
    # 或有 [render] 段（渲染插件声明——覆盖式输出，见 pipeline 渲染分支）。
    grammar = raw.get("grammar", {})
    transform = raw.get("transform", {})
    analyzer = raw.get("analyzer", {})
    pipeline = raw.get("pipeline", {})
    capabilities = raw.get("capabilities", {})
    render = raw.get("render", {})
    if (
        not grammar.get("files")
        and not transform.get("handlers")
        and not analyzer.get("handlers")
        and not analyzer.get("postpasses")
        and not pipeline
        and not capabilities
        and not render.get("handler")
    ):
        return None
    comp = {
        "name": os.path.basename(os.path.dirname(path)),
        "grammar": grammar,
        "analyzer": raw.get("analyzer", {}),
        "transform": raw.get("transform", {}),
        "pipeline": pipeline,
        "capabilities": capabilities,
        "render": render,
    }
    return comp


def _resolve_dependencies(metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topological sort by requires[]. Raises ValueError on cycle/missing."""
    names = {m[META_NAME] for m in metas}
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()

    def _visit(name: str, path: list[str]) -> None:
        if name in visited:
            return
        if name in path:
            raise ValueError(f"Component dependency cycle: {' -> '.join(path + [name])}")
        if name not in names:
            raise ValueError(f"Component '{name}' requires '{name}' but it's not found")
        meta = next(m for m in metas if m[META_NAME] == name)
        for dep in meta.get(META_REQUIRES, []):
            _visit(dep, path + [name])
        visited.add(name)
        ordered.append(meta)

    for m in metas:
        _visit(m[META_NAME], [])
    return ordered


def load_component(meta: dict[str, Any]) -> dict[str, Any]:
    """Load a component: grammar files -> analyzer handlers -> transform handlers."""
    name = meta[META_NAME]
    if name in _loaded_components:
        return _loaded_components[name]

    cdir = meta["_dir"]
    info: dict[str, Any] = {"name": name, "meta": meta}

    # 1. Grammar files
    grammar_meta = meta.get("grammar", {})
    grammar_files = grammar_meta.get("files", [])
    loaded_grammars = []
    for fname in grammar_files:
        fpath = os.path.join(cdir, fname)
        if os.path.isfile(fpath):
            loaded_grammars.append(fpath)
    info["grammar_files"] = loaded_grammars

    # 2. Analyzer handlers
    analyzer_meta = meta.get("analyzer", {})
    info["analyzer"] = _load_python_handlers(
        cdir, analyzer_meta.get("handlers", [])
    )

    # 2b. Analyzer postpasses（遍历后链式走查钩子，ADR-0004）
    info["postpasses"] = _load_postpasses(
        cdir, analyzer_meta.get("postpasses", [])
    )

    # 3. Transform handlers
    transform_meta = meta.get("transform", {})
    info["transform"] = _load_python_handlers(cdir, transform_meta.get("handlers", []))
    # 3b. Transform 槽位契约声明（5b-3c 声明面；须在 handlers import 之后校验）
    info["slot_decls"] = _load_transform_slot_decls(cdir, transform_meta)
    # 3c. Transform ctx 通道声明（槽位 ctx 派生数据的声明式构造）
    info["ctx_channels"] = _load_transform_ctx_channels(cdir, transform_meta)

    # 4. Pipeline pass / schedule 声明（ADR-0007）
    info["pipeline"] = _load_pipeline_decls(cdir, meta.get("pipeline", {}))

    # 5. Capabilities（P2.5 插件回调能力化：能力入口 file.py:fn）
    info["capabilities"] = _load_capabilities(cdir, meta.get("capabilities", {}))

    # 6. Render handler（渲染插件覆盖式：[render] handler = "file.py:fn"，
    #    产出最终文本；管线渲染阶段检测到启用则跳过主管线源端渲染）
    info["render"] = _load_render_handler(cdir, meta.get("render", {}))

    _loaded_components[name] = info
    return info


def load_all_components(plugins_dir: str = "") -> list[dict[str, Any]]:
    """Discover, dependency-sort, and load all components.

    plugins_dir 非空时从指定语言包加载组件（单语言选择）；空时用默认包。
    调用即建立**语言作用域**（`_components_initialized`）——即使该语言没有
    组件（如 yaml），也要知道"当前作用域=空"，否则插件按作用域过滤会退化成
    "不过滤"（见 `transform.engine.active_plugin_classes`）。
    """
    global _components_initialized
    _components_initialized = True
    metas = discover_components(plugins_dir)
    ordered = _resolve_dependencies(metas)
    result = []
    for meta in ordered:
        info = load_component(meta)
        result.append(info)
    # 语言作用域固化：本次装载的组件集就是当前语言的全部组件
    _active_components.clear()
    _active_components.update(info["name"] for info in result)
    return result


def get_component_grammar_files(lang: str = "") -> list[str]:
    """Get grammar file paths for all loaded components, optionally filtered by lang."""
    files = []
    for info in _loaded_components.values():
        meta = info.get("meta", {})
        if lang and meta.get("lang", "*") not in (lang, "*"):
            continue
        files.extend(info.get("grammar_files", []))
    return files


def register_transform_slot(name: str):
    """Decorator: register a transform slot."""
    def decorator(fn):
        _transform_slots[name] = fn
        return fn
    return decorator


def get_transform_slots() -> dict[str, Callable]:
    return dict(_transform_slots)


# 槽位契约声明取值空间（5b-3c）：遍历形态 / 结果接回形态。
_SLOT_WALKS = ("top", "recursive")
_SLOT_RESULTS = ("extra", "none", "replace", "remove")


def _load_transform_slot_decls(cdir: str, transform_meta: dict) -> dict[str, dict]:
    """解析组件 `[[transform.slots]]` 槽位契约声明 → {槽位名: 契约}。

    契约字段（语言知识就地，引擎只按声明里的名字匹配，不内置语言知识）：
        name   槽位名（须与 `@register_transform_slot` 注册名一致 → fail-fast）
        on     触发节点名（字符串或字符串列表）
        walk   遍历形态：`top`（根 sub_node 顶层）/ `recursive`（整树递归）
        ctx    ctx 取值声明 `{键 = "$node" | "<节点名>"}`（`$node` = 触发节点
               自身；节点名 = 该子树里首个同名节点）；引擎固有通道
               （`root_scope` / `type_map`）自动注入，不需声明
        result 结果接回：`extra`（额外输出文件）/ `none`（原地改）/ `replace`
               （1:1 替换 + 注释迁移）/ `remove`（从父列表移除）

    本步只落**声明面**（解析 + 校验）；按声明遍历/调用/接回的**执行面**见 5b-3c-2。
    """
    slots: dict[str, dict] = {}
    for decl in transform_meta.get("slots", []) or []:
        if not isinstance(decl, dict):
            raise ValueError(
                f"[plugin] transform.slots 项须为表（[[transform.slots]]）: "
                f"{decl!r} ({cdir})"
            )
        name = decl.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"[plugin] transform.slots 缺 name: {decl!r} ({cdir})")
        if name in slots:
            raise ValueError(
                f"[plugin] transform.slots 槽位名重复: {name!r} ({cdir})"
            )
        if name not in _transform_slots:
            # 注册副作用是一次性的（模块体已 exec 过），但注册表可能被外部
            # 清理（测试隔离还原 _transform_slots / 热重载）→ 两者失同步。
            # 补注册一次（重新 exec 本组件 handlers；注册为幂等——
            # register_transform_slot 覆盖式、register_primitive 同名同函数幂等）。
            _reload_component_handlers(cdir, transform_meta.get("handlers", []))
        if name not in _transform_slots:
            raise ValueError(
                f"[plugin] transform.slots 槽位 {name!r} 未注册（须由 "
                f"[transform].handlers 的模块 @register_transform_slot）({cdir})"
            )
        on = decl.get("on")
        on_list = [on] if isinstance(on, str) else list(on or [])
        if not on_list or not all(isinstance(o, str) and o for o in on_list):
            raise ValueError(
                f"[plugin] transform.slots '{name}' on 须为非空节点名或其列表 "
                f"({cdir})"
            )
        walk = decl.get("walk", "top")
        if walk not in _SLOT_WALKS:
            raise ValueError(
                f"[plugin] transform.slots '{name}' walk 非法: {walk!r}"
                f"（合法: {_SLOT_WALKS}）({cdir})"
            )
        result = decl.get("result", "none")
        if result not in _SLOT_RESULTS:
            raise ValueError(
                f"[plugin] transform.slots '{name}' result 非法: {result!r}"
                f"（合法: {_SLOT_RESULTS}）({cdir})"
            )
        ctx = decl.get("ctx", {}) or {}
        if not isinstance(ctx, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in ctx.items()
        ):
            raise ValueError(
                f"[plugin] transform.slots '{name}' ctx 须为 {{键 = 来源}} 字符串表 "
                f"({cdir})"
            )
        for src in ctx.values():
            if src.startswith("$") and src != SLOT_CTX_SELF:
                raise ValueError(
                    f"[plugin] transform.slots '{name}' ctx 特殊来源非法: {src!r}"
                    f"（合法: {SLOT_CTX_SELF} 或节点名）({cdir})"
                )
        slots[name] = {
            "name": name,
            "on": on_list,
            "walk": walk,
            "ctx": dict(ctx),
            "result": result,
        }
    return slots


def get_transform_slot_decls() -> dict[str, dict]:
    """合并已加载组件的槽位契约声明（槽位名 → 契约，5b-3c 声明面）。"""
    return _merge_decl_maps(lambda info: info.get("slot_decls", {}))


def _reload_component_handlers(cdir: str, handler_files: list[str]) -> None:
    """强制重新执行组件 handler 模块（补注册副作用；调用方保证注册幂等）。

    用于"模块体已 exec 但注册表被外部清理"的失同步场景——重 exec 会重跑
    模块级 `@register_*`（slot 覆盖式；primitive 同名同函数幂等）。
    """
    for hf in handler_files or []:
        hpath = os.path.join(cdir, hf)
        if not os.path.isfile(hpath):
            continue
        mod_name = f"_comp_{os.path.basename(cdir)}_{hf.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, hpath)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)


def _load_transform_ctx_channels(cdir: str, transform_meta: dict) -> dict[str, dict]:
    """解析组件 `[transform.ctx_channels]` 声明 → {通道名: {symbol_kind, attr}}。

    通道 = 引擎按声明从 scope 树派生、注入槽位 ctx 的数据（引擎不认识
    kind/attr 的含义，只做机械收集）：
        type_map = { symbol_kind = "typed_port", attr = "type_name" }
    """
    out: dict[str, dict] = {}
    raw = transform_meta.get("ctx_channels", {}) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"[plugin] transform.ctx_channels 须为表 ({cdir})")
    for name, decl in raw.items():
        if not isinstance(decl, dict):
            raise ValueError(
                f"[plugin] transform.ctx_channels '{name}' 须为表 ({cdir})"
            )
        kind = decl.get("symbol_kind")
        attr = decl.get("attr")
        if not isinstance(kind, str) or not kind:
            raise ValueError(
                f"[plugin] transform.ctx_channels '{name}' 缺 symbol_kind ({cdir})"
            )
        if not isinstance(attr, str) or not attr:
            raise ValueError(
                f"[plugin] transform.ctx_channels '{name}' 缺 attr ({cdir})"
            )
        out[name] = {"symbol_kind": kind, "attr": attr}
    return out


def get_transform_ctx_channels() -> dict[str, dict]:
    """合并已加载组件的 ctx 通道声明（通道名 → {symbol_kind, attr}）。"""
    return _merge_decl_maps(lambda info: info.get("ctx_channels", {}))


def get_component_mapping_config() -> dict:
    """Collect mapping_entries from all loaded components.

    组件 .py 模块暴露 mapping_entries（表定义），SemanticMappingPlugin 消费。
    （resolve_entries/apply_refs 后处理已随 resolve_refs 原语链删除，P1.5 step 2 B）
    """
    mapping_entries: dict = {}
    for info in _loaded_components.values():
        for mod in info.get("analyzer", []):
            entries = getattr(mod, "mapping_entries", None)
            if entries:
                mapping_entries.update(entries)
    return mapping_entries


def get_primitive_order() -> list[str]:
    """Return merged analyzer primitive execution order from all loaded components."""
    if _PRIMITIVE_ORDER:
        return list(_PRIMITIVE_ORDER)
    seen: set[str] = set()
    for info in _loaded_components.values():
        order = info.get("meta", {}).get("analyzer", {}).get("primitive_order", [])
        for p in order:
            if p not in seen:
                _PRIMITIVE_ORDER.append(p)
                seen.add(p)
    return list(_PRIMITIVE_ORDER)


def _load_pipeline_decls(cdir: str, pipeline_meta: dict) -> dict[str, Any]:
    """加载组件 [pipeline] 声明：pass 定义（handler 解析为可调用）+
    schedule 原始声明。

    pass handler 格式 `file.py:fn`（与 postpass 一致），fail-fast：
    声明了但模块/函数缺失直接报错（ADR-0003）。
    """
    passes: dict[str, dict] = {}
    for p in pipeline_meta.get("pass", []) or []:
        name = p.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"[plugin] pipeline.pass 缺 name: {p!r} ({cdir})")
        decl = dict(p)
        handler_spec = decl.get("handler")
        if handler_spec:
            if not isinstance(handler_spec, str) or ":" not in handler_spec:
                raise ValueError(
                    f"[plugin] pipeline.pass handler 格式应为 'file.py:fn'，"
                    f"收到: {handler_spec!r} ({cdir})"
                )
            fname, fn_name = handler_spec.split(":", 1)
            modules = _load_python_handlers(cdir, [fname])
            if not modules:
                raise ValueError(
                    f"[plugin] pipeline.pass handler 模块不存在: {fname} ({cdir})"
                )
            fn = getattr(modules[0], fn_name, None)
            if fn is None or not callable(fn):
                raise ValueError(
                    f"[plugin] pipeline.pass handler 函数 {fn_name} 不存在于 "
                    f"{fname} ({cdir})"
                )
            decl["_handler"] = fn
        passes[name] = decl
    schedules: dict[str, dict] = {}
    for s in pipeline_meta.get("schedule", []) or []:
        sname = s.get("name")
        if not isinstance(sname, str) or not sname:
            raise ValueError(f"[plugin] pipeline.schedule 缺 name: {s!r} ({cdir})")
        schedules[sname] = s
    # 加工单元实例（ADR-0015 §1）：显式 + 带参数的配置品类。
    # 项形态：{ name, type, impl, after|order?, params? }（name 提到 dict 键）。
    units: dict[str, dict] = {}
    for u in pipeline_meta.get("units", []) or []:
        if not isinstance(u, dict):
            raise ValueError(f"[plugin] pipeline.units 项须为表: {u!r} ({cdir})")
        uname = u.get("name")
        if not isinstance(uname, str) or not uname:
            raise ValueError(f"[plugin] pipeline.units 缺 name: {u!r} ({cdir})")
        udecl = {k: v for k, v in u.items() if k != "name"}
        # 非内置 impl（含 ':'）→ 解析为 handler（与 pass handler 同格式，fail-fast）。
        impl = udecl.get("impl", "")
        if isinstance(impl, str) and ":" in impl and not impl.startswith("builtin."):
            fname, fn_name = impl.split(":", 1)
            modules = _load_python_handlers(cdir, [fname])
            if not modules:
                raise ValueError(
                    f"[plugin] pipeline.units impl 模块不存在: {fname} ({cdir})"
                )
            fn = getattr(modules[0], fn_name, None)
            if fn is None or not callable(fn):
                raise ValueError(
                    f"[plugin] pipeline.units impl 函数 {fn_name} 不存在于 {fname} ({cdir})"
                )
            udecl["_handler"] = fn
        units[uname] = udecl
    return {"passes": passes, "schedules": schedules, "units": units}


def _load_capabilities(cdir: str, caps_meta: dict) -> dict[str, Callable]:
    """加载组件 [capabilities] 声明（能力名 → 入口函数，file.py:fn）。

    能力入口由插件定义返回形态（如 dict 聚合能力 API 面），引擎只做
    查找与调用（P2.5 插件回调能力化——pipeline 不再直接 import
    grammar.<lang> 插件）。fail-fast（ADR-0003）：声明了但模块/函数
    缺失直接报错。
    """
    caps: dict[str, Callable] = {}
    for name, spec in (caps_meta or {}).items():
        if not isinstance(spec, str) or ":" not in spec:
            raise ValueError(
                f"[plugin] capabilities.{name} 声明格式应为 'file.py:fn'，"
                f"收到: {spec!r} ({cdir})"
            )
        fname, fn_name = spec.split(":", 1)
        modules = _load_python_handlers(cdir, [fname])
        if not modules:
            raise ValueError(
                f"[plugin] capabilities.{name} 模块不存在: {fname} ({cdir})"
            )
        fn = getattr(modules[0], fn_name, None)
        if fn is None or not callable(fn):
            raise ValueError(
                f"[plugin] capabilities.{name} 函数 {fn_name} 不存在于 "
                f"{fname} ({cdir})"
            )
        caps[name] = fn
    return caps


def get_capability(name: str) -> Callable | None:
    """按名查找已加载组件声明的能力入口函数（P2.5）。

    [capabilities] 声明格式 '<能力名> = "file.py:fn"'，入口函数返回
    插件定义的能力 API 面（dict 等）。未声明返回 None（调用方降级）；
    声明期错误（模块/函数缺失）在组件加载时已 fail-fast（ADR-0003）。
    """
    for info in _loaded_components.values():
        caps = info.get("capabilities", {})
        if name in caps:
            return caps[name]
    return None


def get_capability_in(name: str, root_dir: str) -> Callable | None:
    """在指定语言包目录下查找能力入口（未声明 → None）。

    与 `get_capability` 的区别：**按组件来源目录限定**，不依赖"当前装载语言"的
    全局状态——按 rules_dir 工作的消费点（预处理器等）用它避开跨语言串用：
    只有该语言包 `plugins/` 下的组件才有资格应答。
    """
    root = os.path.normcase(os.path.abspath(root_dir)) + os.sep
    for info in _loaded_components.values():
        cdir = str((info.get("meta") or {}).get("_dir") or "")
        if not cdir or not os.path.normcase(os.path.abspath(cdir)).startswith(root):
            continue
        cap = (info.get("capabilities") or {}).get(name)
        if cap is not None:
            return cap
    return None


def _merge_decl_maps(pick: Callable[[dict], dict]) -> dict[str, dict]:
    """合并所有已加载组件在 `pick(info)` 上的声明表（浅合并，后载覆盖）。

    统一 `slot_decls` / `ctx_channels` / `pipeline.{passes,schedules,units}`
    五处同形遍历；`pick` 直接给出取值路径，保持原有取值语义（缺键 → {}，
    值为 None → 原样交给 `update` 报错，不在此处放宽）。
    """
    merged: dict[str, dict] = {}
    for info in _loaded_components.values():
        merged.update(pick(info))
    return merged


def get_pipeline_pass_decls() -> dict[str, dict]:
    """合并所有已加载组件的 pipeline.pass 声明（ADR-0007）。"""
    return _merge_decl_maps(lambda info: info.get("pipeline", {}).get("passes", {}))


def get_pipeline_schedules() -> dict[str, dict]:
    """合并所有已加载组件的 pipeline.schedule 声明（ADR-0007）。"""
    return _merge_decl_maps(lambda info: info.get("pipeline", {}).get("schedules", {}))


def get_pipeline_units() -> dict[str, dict]:
    """合并所有已加载组件的 pipeline.units 声明（ADR-0015 §1 加工单元实例）。"""
    return _merge_decl_maps(lambda info: info.get("pipeline", {}).get("units", {}))


def get_analyzer_postpass_decls() -> list[dict[str, Any]]:
    """合并所有已加载组件的 postpass 声明（保持**声明序**）。

    每条：`{"name", "fn", "produces", "requires"}`——`name` = `file.py:fn`
    （链内轨迹/诊断标识），`fn` = 已解析函数（签名 `fn(analyzer, context)`）。
    顺序 = 组件装载序（`discover_components` 按组件名排序）；链内依赖靠
    `produces`/`requires` 声明并被 `AnalysisTraversal` 校验，不靠名字顺序碰巧成立。
    """
    decls: list[dict[str, Any]] = []
    for info in _loaded_components.values():
        decls.extend(info.get("postpasses", []))
    return decls


def _name_list(value: Any, field: str, run: str, cdir: str) -> list[str]:
    """postpass 契约名列表字段核验（缺省 = 空；非字符串列表 → fail-fast）。"""
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(v, str) or not v for v in value
    ):
        raise ValueError(
            f"[plugin] postpass '{run}' {field} 须为非空字符串列表: "
            f"{value!r} ({cdir})"
        )
    return list(value)


def _load_postpasses(cdir: str, postpass_specs: list) -> list[dict[str, Any]]:
    """加载 `[[analyzer.postpasses]]` 声明（表形态，保持声明序）。

    形态：

        [[analyzer.postpasses]]
        run = "_expand_ports.py:run_expand_ports"
        produces = ["resolved_ports"]   # 可选：本环节产出名
        requires = ["resolved_ports"]   # 可选：本环节依赖名

    契约语义 = **链内时点可达性**：`requires` 须由链上更早环节的 `produces`、
    `scope` 或链开始时 `context.extra` 已有的键提供，否则 fail-fast。
    不核验物化（postpass 产物写在符号表/context 上，引擎不懂其语义）——
    与 transform 单元契约的区别见 `analyzer/semantic_checks.md`。
    fail-fast（ADR-0003）：非表 / 未知键 / `run` 格式 / 模块 / 函数任一不合法即报错。
    """
    decls: list[dict[str, Any]] = []
    for spec in postpass_specs or []:
        if not isinstance(spec, dict):
            raise ValueError(
                f"[plugin] postpass 声明须为表（[[analyzer.postpasses]] + run），"
                f"收到: {spec!r} ({cdir})"
            )
        unknown = set(spec) - {"run", "produces", "requires"}
        if unknown:
            raise ValueError(
                f"[plugin] postpass 声明含未知键: {', '.join(sorted(unknown))}"
                f"（支持 run/produces/requires）({cdir})"
            )
        run = spec.get("run")
        if not isinstance(run, str) or ":" not in run:
            raise ValueError(
                f"[plugin] postpass.run 格式应为 'file.py:fn'，收到: {run!r} ({cdir})"
            )
        produces = _name_list(spec.get("produces"), "produces", run, cdir)
        requires = _name_list(spec.get("requires"), "requires", run, cdir)
        fname, fn_name = run.split(":", 1)
        modules = _load_python_handlers(cdir, [fname])
        if not modules:
            raise ValueError(f"[plugin] postpass 模块不存在: {fname} ({cdir})")
        fn = getattr(modules[0], fn_name, None)
        if fn is None or not callable(fn):
            raise ValueError(
                f"[plugin] postpass 函数 {fn_name} 不存在于 {fname} ({cdir})"
            )
        decls.append(
            {"name": run, "fn": fn, "produces": produces, "requires": requires}
        )
    return decls


def _load_render_handler(cdir: str, render_meta: dict) -> Callable | None:
    """加载组件 [render] 段声明的渲染入口（`handler = "file.py:fn"`）。

    渲染插件覆盖式（与 analyze/transform 的叠加式不同）：启用后管线渲染
    阶段直接调用该 handler 产出最终文本（如 c4 汇编），跳过主管线源端
    渲染。未声明 [render] 段 → None（主管线渲染）。fail-fast（ADR-0003）：
    声明了但模块/函数缺失直接报错。
    """
    handler_spec = render_meta.get("handler") if render_meta else None
    if not handler_spec:
        return None
    if not isinstance(handler_spec, str) or ":" not in handler_spec:
        raise ValueError(
            f"[plugin] render.handler 声明格式应为 'file.py:fn'，"
            f"收到: {handler_spec!r} ({cdir})"
        )
    fname, fn_name = handler_spec.split(":", 1)
    modules = _load_python_handlers(cdir, [fname])
    if not modules:
        raise ValueError(
            f"[plugin] render.handler 模块不存在: {fname} ({cdir})"
        )
    fn = getattr(modules[0], fn_name, None)
    if fn is None or not callable(fn):
        raise ValueError(
            f"[plugin] render.handler 函数 {fn_name} 不存在于 {fname} ({cdir})"
        )
    return fn


def get_render_handler(name: str) -> Callable | None:
    """按组件名取已加载组件的渲染入口（[render] handler，file.py:fn）。

    未声明 [render] 段或组件不存在 → None（主管线渲染，调用方降级）。
    声明期错误（模块/函数缺失）在组件加载时已 fail-fast（ADR-0003）。
    """
    info = _loaded_components.get(name)
    if info is None:
        return None
    return info.get("render")


def _load_python_handlers(cdir: str, handler_files: list[str]) -> list[Any]:
    """Load Python handler files from a component directory.

    幂等：模块已在 sys.modules（同进程重复加载组件）则直接复用，不重复
    exec_module——否则 @register 的 analyzer primitive / transform slot 会
    重复注册抛 ValueError（setup_grammar 单语言重建组件时触发）。
    """
    modules = []
    for hf in handler_files:
        hpath = os.path.join(cdir, hf)
        if not os.path.isfile(hpath):
            continue
        mod_name = f"_comp_{os.path.basename(cdir)}_{hf.replace('.', '_')}"
        if mod_name in sys.modules:
            modules.append(sys.modules[mod_name])
            continue
        spec = importlib.util.spec_from_file_location(mod_name, hpath)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            modules.append(mod)
    return modules



