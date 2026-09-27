"""ConfigRegistry — 声明式配置注册中心。

用法:
    # 1. 在管线启动点统一加载
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all(rules_dir, ext_dirs=ext_dirs)

    # 2. 使用（key 为 "lexer.xxx" / "pratt.xxx" / "renderer.xxx" 等）
    cats = config.get("parser.token_categories")

配置声明自动从 grammar 包的 tpc.toml 中读取 [xxx] 注册（grammar 段落除外）。

Doc: core/config_lifecycle.md
"""

import os
import json
import re
import tomllib
from typing import Any, TypeVar

from core.errors import ConfigError
from core.engine_compat import check_engine_compat

# 配置文件定位：单一实现在 core/_user_config.py（历史：本文件与 core/define.py
# 各有一份拷贝），re-export 供 main.py / tests 从本模块导入。
from core._user_config import find_user_config as _find_user_config


def _glob_to_regex(pattern: str) -> re.Pattern:
    """将 glob 风格模式（支持 * 和 ?）编译为正则对象。"""
    pattern = pattern.replace("/", os.sep).replace("\\", os.sep)  # 统一分隔符
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(f"^{escaped}$")


def _glob_match(patterns: list[str], base_dir: str) -> list[str]:
    """用 os + re 实现的 glob 匹配，返回绝对路径列表。

    支持的 pattern 格式：
        "*.toml"       → base_dir 下所有 .toml 文件
        "0*.toml"      → base_dir 下以 0 开头的 .toml 文件
        "0*/*.toml"    → base_dir 下以 0 开头的子目录中的 .toml 文件

    两条路径：pattern 不含目录分隔符 → 平铺匹配文件名（`_match_flat`）；
    含分隔符 → 递归匹配相对路径（`_match_recursive`）。
    """
    compiled = [_glob_to_regex(p) for p in patterns]
    # 统一分隔符后再用 os.sep 判断，跨平台兼容
    has_dir = any(os.sep in p.replace("/", os.sep) for p in patterns)
    try:
        if has_dir:
            results = _match_recursive(compiled, base_dir)
        else:
            results = _match_flat(compiled, base_dir)
    except PermissionError as exc:
        # 静默跳过不可读目录 = 规则文件静默缺失（token.toml 事故形态）
        # → fail-fast（见 core/config_lifecycle.md「fail-fast」）
        raise ConfigError(
            f"[config] 目录不可读，无法匹配规则文件: {base_dir}（{exc}）"
        ) from exc
    return sorted(results)


def _match_flat(compiled: list, base_dir: str) -> list[str]:
    """平铺匹配：只比 base_dir 下的**文件名**（pattern 不含目录分隔符）。"""
    results: list[str] = []
    for entry in os.scandir(base_dir):
        if entry.is_file() and _any_match(compiled, entry.name):
            results.append(entry.path)
    return results


def _match_recursive(compiled: list, base_dir: str) -> list[str]:
    """含目录分隔符的 pattern：逐层比**相对路径**（文件与子目录都参与）。"""
    results: list[str] = []
    for root, dirs, files in os.walk(base_dir):
        rel_root = os.path.relpath(root, base_dir)
        if rel_root == ".":
            rel_root = ""
        for name in files + dirs:
            rel_path = os.path.join(rel_root, name)
            if _any_match(compiled, rel_path):
                results.append(os.path.join(root, name))
    return results


def _any_match(compiled: list, candidate: str) -> bool:
    """候选名是否命中任一 pattern（原"命中即 break"语义——只关心是否命中）。"""
    return any(regex.match(candidate) for regex in compiled)

# ──────────────────────────────────────────────
# 配置声明加载（从 grammar 包 tpc.toml 读取 [config.*]）
# ──────────────────────────────────────────────


def _find_grammar_tpc_toml() -> str:
    """Locate the grammar package's tpc.toml."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    user_config = _find_user_config()
    grammar_dir = ""
    if user_config:
        try:
            with open(user_config, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            # 用户配置损坏 → fail-fast（与 core/define.py 同策略）：静默回退到
            # 默认语言包会让用户的 grammar 设置"看起来生效"却没有
            raise ConfigError(f"[config] {user_config} 读取/解析失败: {exc}") from exc
        g = cfg.get("grammar", "")
        if isinstance(g, str):
            grammar_dir = g
        elif isinstance(g, dict):
            grammar_dir = g.get("rules_dir", "")
        else:
            raise ConfigError(f"[config] {user_config} 的 grammar 段应为字符串或对象")
    # 用户配置缺失（wheel 安装后无项目 config/tpc_config.json）时回退默认语言包。
    # root 在 editable（项目根）与 wheel（site-packages）两种模式下都指向
    # grammar 包所在目录的父级，故 root/grammar/verilog 两种模式均可定位。
    if not grammar_dir:
        grammar_dir = "grammar/verilog"
    meta_path = os.path.join(root, grammar_dir, "tpc.toml")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"[config] Grammar package tpc.toml not found: {meta_path}"
        )
    return meta_path


# 文件式配置声明的合法字段（tpc.toml [xxx] 段内）
_DECL_FIELDS = {"file", "section", "required", "base", "description"}


def _flatten_config(table: dict, prefix: str = "") -> list:
    """Recursively flatten nested config table into (dotted_key, spec) pairs."""
    result = []
    for key, value in table.items():
        full_key = f"{prefix}.{key}" if prefix else key
        # dict 无 file 且不含声明字段 → 递归展开（嵌套 bare data）；
        # 含声明字段但缺 file（如 { section = "x" }）→ 不展开，作为 spec
        # 交给 _validate_decl_spec 拦截（疑似忘了 file 的文件式声明）。
        if (
            isinstance(value, dict)
            and "file" not in value
            and not (set(value) & _DECL_FIELDS)
        ):
            result.extend(_flatten_config(value, full_key))
        else:
            result.append((full_key, value))
    return result


def deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 到 base（dict 嵌套合并，非 dict 值后者优先）。

    用于同名配置 key 的多来源合并（多插件 token_ext 等）：浅 update 会让
    后加载的顶层 key（如 [id]）整体覆盖前一个，深合并保留嵌套结构。
    单一实现：配置加载（本模块）与 `lexer/lexer_utils.merge_token_define`
    共用；需要深合并的新调用方直接 import 本函数，不要再拷一份。
    """
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _validate_file_spec_fields(config_key: str, spec: dict) -> None:
    """文件式声明字段校验：file / section / required / base（类型错 → fail-fast）。"""
    f = spec["file"]
    if not (isinstance(f, str) or (isinstance(f, list) and all(isinstance(x, str) for x in f))):
        raise ConfigError(
            f"[config] {config_key}: file 必须是字符串或字符串列表，got {type(f).__name__}"
        )
    sec = spec.get("section")
    if sec is not None and not isinstance(sec, str):
        raise ConfigError(
            f"[config] {config_key}: section 必须是字符串或 None，got {type(sec).__name__}"
        )
    req = spec.get("required", True)
    if not isinstance(req, bool):
        raise ConfigError(
            f"[config] {config_key}: required 必须是布尔值，got {type(req).__name__}"
        )
    base = spec.get("base", "rules")
    if not isinstance(base, str):
        raise ConfigError(
            f"[config] {config_key}: base 必须是字符串，got {type(base).__name__}"
        )


def _validate_bare_spec(config_key: str, spec: dict) -> None:
    """无 file 的 dict：含声明字段 = 疑似"忘了 file" → 拦截；否则合法裸配置。"""
    decl_like = set(spec) & {"section", "required", "base", "description"}
    if decl_like:
        raise ConfigError(
            f"[config] {config_key}: 疑似文件式声明但缺 file 字段"
            f"（含 {sorted(decl_like)}）。文件式声明需 file = \"...\"。"
        )


def _validate_enabled_arg(enabled: list[str], pack: str) -> tuple[str, ...]:
    """`enabled=` 参数校验（fail-fast）：非空字符串列表 → 元组。

    写错的档位必须当场喊出来：静默忽略会让"启用组合等效某标准"变成空话
    （少加载了插件，却看起来一切正常）。
    """
    if not isinstance(enabled, list):
        raise ConfigError(
            f"[plugins] enabled 覆盖参数必须是字符串列表，得到 "
            f"{type(enabled).__name__}（包 {pack}）"
        )
    for name in enabled:
        if not isinstance(name, str) or not name:
            raise ConfigError(
                f"[plugins] enabled 覆盖参数含非法项 {name!r}（须为非空字符串）"
                f"（包 {pack}）"
            )
    return tuple(enabled)


def _validate_decl_spec(config_key: str, spec: Any) -> None:
    """校验 tpc.toml 配置声明结构（fail-fast，schema 化第一步）。

    文件式声明：spec 必须是 dict 且含 "file"（str 或 list[str]），
    section/required/base/description 类型合法，无未知字段。
    bare data：spec 非 dict，或 dict 但无任何声明字段（合法裸配置）。

    防护：声明结构错误（忘了 file、拼错字段、类型错）静默通过会导致
    配置加载错乱（如文件式声明被当 bare data 注册），fail-fast 拦截。
    """
    if not isinstance(spec, dict):
        return  # 非 dict → 合法 bare data（如 [analyzer] primitives = [...]）
    unknown = set(spec) - _DECL_FIELDS
    if unknown:
        raise ConfigError(
            f"[config] {config_key}: 声明含未知字段 {sorted(unknown)}。"
            f"合法字段: {sorted(_DECL_FIELDS)}"
        )
    if "file" in spec:
        _validate_file_spec_fields(config_key, spec)
        return
    _validate_bare_spec(config_key, spec)


# 组件 tpc.toml 索引：plugins 树 → {组件名: (tpc 绝对路径, 相对 plugins 的目录)}。
# 按 `plugins_dir` 建一次（动机与键控口径见 `_plugin_tpc_index`）。
_PLUGIN_TPC_INDEX: dict[str, dict[str, tuple[str, str]]] = {}


def _find_plugin_tpc(package_dir: str, name: str) -> tuple[str, str]:
    """在 plugins/ 目录树递归查找组件 <name>/tpc.toml（聚类目录支持）。

    返回 (tpc 绝对路径, 相对 plugins/ 的目录路径，如 "name" 或 "checks/name")。
    未找到返回 ("", "")——enabled 列表引用未安装组件时静默跳过（与平铺时代
    行为一致：组件缺失不阻断配置声明收集）。
    """
    plugins_dir = os.path.join(package_dir, "plugins")
    if not os.path.isdir(plugins_dir):
        return "", ""
    return _plugin_tpc_index(plugins_dir).get(name, ("", ""))


def _plugin_tpc_index(plugins_dir: str) -> dict[str, tuple[str, str]]:
    """一次遍历建 `{组件名: (tpc 路径, 相对 plugins 的目录)}`（同名取遍历序首个）。

    动机（2026-09-22 实测）：`_find_plugin_tpc` 原按**组件名逐个** `os.walk` 全树
    搜索，而 `_load_meta_declarations` 在一次 check 里被反复调用 → 一个只含小样例的
    `check()` 实测该函数被调 **130 次**、`os.walk` **2740 次**（0.136s/次 check）；
    全量测试里这是可观的重复劳动。改为**按目录建一次**索引后按名取（与 analyzer 侧
    已验收的 `ModuleIndexer.dir_module_files` 同型）。

    键 = plugins_dir：纯字符串索引、无跨运行可变对象（与 `macro_shape._PARSE_CACHE`
    同类的纯函数缓存，故登记在 `CONTENT_ADDRESSED`）。⚠ 若在同一路径上**改写**
    plugins 树需清索引；现有测试都用独立 tmp 目录，键不同、不会命中陈旧项。
    """
    idx = _PLUGIN_TPC_INDEX.get(plugins_dir)
    if idx is not None:
        return idx
    idx = {}
    for root, dirs, files in os.walk(plugins_dir):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        if "tpc.toml" not in files:
            continue
        # setdefault：与原"逐名遍历、命中即返回"取同一个（遍历序首个）
        idx.setdefault(
            os.path.basename(root),
            (
                os.path.join(root, "tpc.toml"),
                os.path.relpath(root, plugins_dir).replace("\\", "/"),
            ),
        )
    _PLUGIN_TPC_INDEX[plugins_dir] = idx
    return idx


def _load_meta_declarations(
    grammar_dir: str = "", enabled: list[str] | None = None
) -> list[tuple]:
    """Read [config.*] declarations from grammar package tpc.toml files.

    Args:
        grammar_dir: 语言包目录（相对项目根，如 "grammar/c4"）。空时用
            默认包（config/tpc_config.json 指向的 grammar）——保持既有单语言
            行为；第二语言（c4 等）通过 ConfigRegistry.load_language 传入。
        enabled: **启用组合覆盖**（插件名列表；`None` = 用包内 `[plugins] enabled`）。
            这就是"档位对照"的一等入口：同一次进程内 `enabled=["c11"]` → `enabled=[]`
            让词法/配置声明按档位重建（不必再改 pack 文件或复制 pack）。

    两块来源：语言包自身 tpc.toml（`_core_declarations`）+ `[plugins] enabled`
    列出的插件 tpc.toml（`_plugin_declarations`）；两块的声明元组形状由
    `_file_decl` / `_bare_decl` 统一（core 与插件的 base/required 缺省不同）。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. Language package tpc.toml（含 [engine] 兼容校验）
    if grammar_dir:
        core_path = os.path.join(root, grammar_dir, "tpc.toml")
        if not os.path.isfile(core_path):
            raise ConfigError(
                f"[config] grammar package tpc.toml not found: {core_path}"
            )
    else:
        core_path = _find_grammar_tpc_toml()
    with open(core_path, encoding="utf-8") as f:
        meta = tomllib.loads(f.read())
    # 引擎 API 兼容校验（[engine] 段，fail-fast）——该段是包与引擎的契约声明，
    # 不是配置声明，下面注册时跳过（否则会被当 bare data 注册进配置中心）
    check_engine_compat(meta, grammar_dir or core_path)
    declarations = _core_declarations(meta)

    # 2. Plugin packages — 启用组合（显式覆盖 > 包内 [plugins] enabled）
    _plugin_declarations(
        os.path.dirname(core_path), meta, declarations, enabled=enabled
    )
    return declarations


def _core_declarations(meta: dict) -> list[tuple]:
    """语言包 tpc.toml → 声明元组列表（跳过 `grammar` / `engine` 两段）。"""
    declarations: list[tuple] = []
    for ns, table in meta.items():
        if ns in ("grammar", "engine"):
            continue
        for config_key, spec in _flatten_config({ns: table}):
            _validate_decl_spec(config_key, spec)
            if _is_file_spec(spec):
                # 文件式配置：file 为字符串路径或列表模式
                declarations.append(
                    _file_decl(config_key, spec.get("file", ""), spec, "rules", True)
                )
            else:
                # 非文件式配置，以 bare data 形式注册
                declarations.append(_bare_decl(config_key, spec))
    return declarations


def _plugin_specs(plugin_meta: dict):
    """插件 tpc.toml → (config_key, spec) 逐条（跳过 `grammar` 段）。"""
    for ns, table in plugin_meta.items():
        if ns == "grammar":
            continue
        yield from _flatten_config({ns: table})


def _append_plugin_spec(
    config_key: str, spec: dict, rel_dir: str, declarations: list
) -> None:
    """单条插件声明：文件式合并 file 列表；非文件式以 bare data 注册。"""
    _validate_decl_spec(config_key, spec)
    if _is_file_spec(spec):
        _append_plugin_file_decl(config_key, spec, rel_dir, declarations)
        return
    # 非文件式配置（bare data）——插件 tpc.toml 里也可能有裸配置
    # （[namespace].foo 点路径键，如插件自身的开关项）。缺此分支会导致插件
    # 裸配置从未注册（历史 bug）。
    declarations.append(_bare_decl(config_key, spec))


def _plugin_declarations(
    package_dir: str,
    meta: dict,
    declarations: list,
    enabled: list[str] | None = None,
) -> None:
    """启用组合列出的插件 tpc.toml → 声明追加进 `declarations`。

    启用组合来源：`enabled` 显式给出时用它（**档位覆盖**），否则读包内
    `[plugins] enabled`。两者都做**结构校验（fail-fast）**：非字符串列表 /
    含空串 / 含非字符串 → ConfigError——写错的档位必须喊出来，不能静默少加载
    插件（那会让"启用组合等效某标准"变成一句空话）。

    插件声明与语言包同形，但两处不同：base 固定 `plugins`（file 路径带插件
    相对目录前缀）、required 缺省 **False**（插件可选）；同名 config_key 的
    多插件来源**合并 file 列表**（见 `_append_plugin_file_decl`）。

    ⚠ 插件的 **Python 组件与规则文件** 不在这里加载（那条路径是
    `setup_grammar` → `load_all_components`），故本函数只决定"词法/配置声明面"。
    """
    plugins_cfg = meta.get("plugins", {})
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
    names = enabled if enabled is not None else plugins_cfg.get("enabled", [])
    if not isinstance(names, list):
        raise ConfigError(
            f"[plugins] enabled 必须是字符串列表，得到 {type(names).__name__}"
            f"（包 {os.path.basename(package_dir)}）"
        )
    for name in names:
        if not isinstance(name, str) or not name:
            raise ConfigError(
                f"[plugins] enabled 含非法项 {name!r}（须为非空字符串）"
                f"（包 {os.path.basename(package_dir)}）"
            )
        plugin_tpc, rel_dir = _find_plugin_tpc(package_dir, name)
        if not plugin_tpc:
            # fail-fast：清单里的名字必须能解析到插件包。此前静默跳过 ⇒ 拼错一个
            # 名字就少加载一个插件而毫无提示（"启用组合等效某标准"直接失真）。
            raise ConfigError(
                f"[plugins] enabled 列了 {name!r}，但 {package_dir} 下找不到该插件包"
                f"（需要 <plugins>/{name}/tpc.toml 或同名分类子目录）"
            )
        with open(plugin_tpc, encoding="utf-8") as f:
            plugin_meta = tomllib.loads(f.read())
        for config_key, spec in _plugin_specs(plugin_meta):
            _append_plugin_spec(config_key, spec, rel_dir, declarations)


def _append_plugin_file_decl(
    config_key: str, spec: dict, rel_dir: str, declarations: list
) -> None:
    """插件文件式声明：file 路径加插件相对目录前缀，同名 key 合并 file 列表。

    合并理由：多插件声明同一扁平 key（token_ext 等）时，不合并则后加载覆盖
    先加载，只保留一个插件来源（违反 resolve 的深合并语义）。
    """
    file_spec = spec["file"]
    prefixed = file_spec
    if isinstance(file_spec, str):
        prefixed = f"{rel_dir}/{file_spec}"
    elif isinstance(file_spec, list):
        prefixed = [f"{rel_dir}/{f}" for f in file_spec]
    for i, d in enumerate(declarations):
        if d[0] != config_key or d[3] != "plugins":
            continue
        old = declarations[i]
        old_files = old[1]
        if isinstance(old_files, str):
            old_files = [old_files]
        new_files = old_files + (
            [prefixed] if isinstance(prefixed, str) else prefixed
        )
        # 保留先到者的 section/required/description（首个声明者为准）
        declarations[i] = (
            config_key,
            new_files,
            old[2],
            "plugins",
            old[4],
            old[5],
            None,
        )
        return
    declarations.append(_file_decl(config_key, prefixed, spec, "plugins", False))


def _is_file_spec(spec: Any) -> bool:
    """声明是否为文件式（spec 是 dict 且 file 为字符串或列表）。"""
    return isinstance(spec, dict) and isinstance(spec.get("file"), (str, list))


def _file_decl(
    config_key: str, file_spec: Any, spec: dict, base_key: str, required_default: bool
) -> tuple:
    """文件式声明元组（7 元，供 `_resolve_decls` 消费）。

    语言包：base=`rules`、required 缺省 True；插件：base=`plugins`、缺省 False。
    """
    return (
        config_key,
        file_spec,
        spec.get("section"),
        base_key,
        spec.get("required", required_default),
        spec.get("description", ""),
        None,
    )


def _bare_decl(config_key: str, spec: Any) -> tuple:
    """非文件式（bare data）声明元组：值随声明直接给（file/section 留空）。"""
    return (config_key, "", None, "", False, "", spec)

_DECLARATIONS = _load_meta_declarations()


def _install_config_declarations():
    """注册所有配置声明（模块导入时自动执行）。"""
    for name, file, section, base, required, desc, bare_value in _DECLARATIONS:
        config.declare(
            name,
            file=file,
            section=section,
            base=base,
            required=required,
            description=desc,
            bare_value=bare_value,
        )


class ConfigRegistry:
    """配置注册中心。"""

    _entries: dict[str, dict] = {}
    _loaded: dict[str, Any] = {}
    _resolved: bool = False
    # 当前 _entries 来源的语言包目录（相对项目根）。None = 尚未按语言包生成
    # （import 期默认包声明）。load_all 时若 rules_dir 与来源不一致，先按该
    # 语言包 tpc.toml 重新生成声明——解决"glob 匹配用默认包、换语言失效"。
    _entries_source: str | None = None
    # 生成 _entries 时用的**启用组合**（插件名元组）。与 _entries_source 一起构成
    # "这份声明是按哪个 (包, 档位) 生成的"判据——少了它，同包切档会静默复用上一档
    # 声明（症状：改了 enabled 毫无变化）。
    _entries_enabled: tuple[str, ...] | None = None
    # 各语言包"当前选定的启用组合"（`load_language/load_all` 登记）。隐式消费方
    # （`resolve` → Lexer / 数字形态）按它解析，从而**无需**给每个消费方加参数就能
    # 跟随档位；未曾 load 过的包回退到包内 `[plugins] enabled`。
    _active_enabled: dict[str, tuple[str, ...]] = {}
    # 包内 `[plugins] enabled` 的读取缓存（档位判定的兜底来源；包文件进程内不变）
    _declared_enabled_cache: dict[str, tuple[str, ...]] = {}
    # 最近一次 load_all 的配置来源（name → {file, section} 或 {bare: True}）。
    # 供调试/可观测（tpc config dump）——回答"这个值从哪来"。
    _sources: dict[str, dict] = {}
    # resolve() 按语言包参数缓存（纯函数语义：同参数结果相同）。
    # 避免每次 Lexer 构造都重新解析全部 TOML 文件（测试中 Lexer 构造频繁）。
    _resolve_cache: dict[tuple, tuple] = {}

    @classmethod
    def declare(
        cls,
        name: str,
        *,
        file: str | list[str],
        section: str | None = None,
        required: bool = True,
        base: str = "rules",
        description: str = "",
        bare_value: Any = None,
    ) -> None:
        """声明一个配置依赖。

        Args:
            name: 配置唯一标识名
            file: TOML 文件路径（相对 base 目录），空字符串表示 bare data
            section: TOML 中的 section key
            required: 加载失败是否致命
            base: 基准目录名
            description: 人类可读描述
            bare_value: 非文件式配置的原始值（如列表）
        """
        if name in cls._entries:
            return  # 重复声明安全无害
        cls._entries[name] = {
            "file": file,
            "section": section,
            "required": required,
            "base": base,
            "description": description,
            "bare_value": bare_value,
        }

    # ── 启用组合（档位）────────────────────────

    @staticmethod
    def _normalize_pack(rules_dir: str) -> str:
        """rules_dir → 语言包目录（相对项目根）；无 tpc.toml 时原样返回。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate = rules_dir
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            candidate = os.path.join("grammar", rules_dir)
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            return rules_dir  # 非语言包目录（低层契约）：保持原样
        return candidate

    @staticmethod
    def _is_pack(candidate: str) -> bool:
        """candidate 是否为语言包目录（含 tpc.toml）。低层契约（临时目录）返回 False。"""
        return os.path.isfile(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                candidate,
                "tpc.toml",
            )
        )

    @classmethod
    def _declared_enabled(cls, pack: str) -> tuple[str, ...]:
        """包内 `[plugins] enabled`（读一次缓存；非语言包目录 → 空元组）。"""
        if not cls._is_pack(pack):
            return ()
        hit = cls._declared_enabled_cache.get(pack)
        if hit is not None:
            return hit
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), pack, "tpc.toml"
        )
        with open(path, encoding="utf-8") as f:
            meta = tomllib.loads(f.read())
        plugins_cfg = meta.get("plugins", {})
        names = plugins_cfg.get("enabled", []) if isinstance(plugins_cfg, dict) else []
        if not isinstance(names, list):
            raise ConfigError(f"[plugins] enabled 必须是字符串列表（包 {pack}）")
        for name in names:
            if not isinstance(name, str) or not name:
                raise ConfigError(
                    f"[plugins] enabled 含非法项 {name!r}（须为非空字符串）（包 {pack}）"
                )
        cls._declared_enabled_cache[pack] = tuple(names)
        return cls._declared_enabled_cache[pack]

    @classmethod
    def _tier_for_load(cls, pack: str, enabled: list[str] | None) -> tuple[str, ...]:
        """**加载**时的档位：显式参数 > 包内清单（None = 用包默认，非"沿用上次"）。"""
        if enabled is None:
            return cls._declared_enabled(pack)
        return _validate_enabled_arg(enabled, pack)

    @classmethod
    def _tier_for_resolve(cls, pack: str, enabled: list[str] | None) -> tuple[str, ...]:
        """**解析**（隐式消费方：Lexer / 数字形态）时的档位：
        显式参数 > `load_language` 登记过的该包档位 > 包内清单。"""
        if enabled is not None:
            return _validate_enabled_arg(enabled, pack)
        hit = cls._active_enabled.get(pack)
        if hit is not None:
            return hit
        return cls._declared_enabled(pack)

    @classmethod
    def _ensure_entries_for(
        cls, rules_dir: str, enabled: tuple[str, ...] | None = None
    ) -> str:
        """确保 _entries 声明来自指定语言包的**指定档位**，返回规范化 rules_dir。

        判据是 `(_entries_source, _entries_enabled)` 二元组：任一变化都重新生成声明。
        ⚠ 只比 rules_dir 会让"同包切档"静默复用上一档声明（实测症状：改了 enabled
        毫无变化）——这正是上一轮该功能没生效的根因之一。
        若 rules_dir 无 tpc.toml（临时目录等低层用法），保持现有 _entries
        不变（load_all 只换 base 目录），兼容直接 declare + load_all 的契约。
        """
        candidate = cls._normalize_pack(rules_dir)
        if not cls._is_pack(candidate):
            return rules_dir  # 非语言包目录：保持现有声明（低层契约）
        tier = enabled if enabled is not None else cls._tier_for_load(candidate, None)
        if cls._entries_source != candidate or cls._entries_enabled != tier:
            decls = _load_meta_declarations(
                grammar_dir=candidate, enabled=list(tier)
            )
            cls._entries.clear()
            for name, file, section, base, required, desc, bare in decls:
                cls.declare(
                    name,
                    file=file,
                    section=section,
                    base=base,
                    required=required,
                    description=desc,
                    bare_value=bare,
                )
            cls._entries_source = candidate
            cls._entries_enabled = tier
        return candidate

    @classmethod
    def load_language(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
        enabled: list[str] | None = None,
    ) -> None:
        """加载指定语言包（**单语言选择**）：从 rules_dir 的 tpc.toml 重新生成
        配置声明并加载全部配置。

        架构约束：
        - 管线**一次只使用一种语言的语法**——本方法在初始化时选一个语言包
          （c4 或 verilog），加载后替换全部声明，不与其他语言混合共存。
        - **非运行中热重载**：语言切换 = 重新初始化管线（改 config 指向 +
          重启，或测试/验证时显式 load_language），不提供热切换 API。
        - 默认 import 期只从 config/tpc_config.json 指向的单一 grammar 包注册
          声明（单语言假设）；本方法供第二语言（c4 等）验证时选择语言包。

        Args:
            rules_dir: 语言包目录（相对项目根，如 "grammar/c4" 或 "c4"）。
            ext_dirs: 额外的扩展规则目录（多语言混合的旧通道）。
            plugins_dir: 兼容参数（当前实现按 `<pack>/plugins` 自动定位）。
            enabled: **启用组合覆盖**（插件名列表）。`None` = 用包内
                `[plugins] enabled`。给定时该组合被登记为该包"当前档位"，
                后续按该包解析配置（词法/数字形态）都沿用——于是"同一 pack、
                同一次进程内切档"成立（判据见
                `tests/languages/c/test_c_standard_tiers.py`）。
        """
        rules_dir = cls._ensure_entries_for(rules_dir, cls._tier_for_load(
            cls._normalize_pack(rules_dir), enabled
        ))
        cls.load_all(
            rules_dir, ext_dirs=ext_dirs, plugins_dir=plugins_dir, enabled=enabled
        )

    @classmethod
    def load_all(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
        enabled: list[str] | None = None,
        **base_dirs: str,
    ) -> None:
        """加载所有已声明的配置。

        每个声明的 file 路径根据其 base 参数选基准目录拼接：
        - base="rules" 用 rules_dir（默认）
        - base="ext" 用 ext_dirs[0]（兼容单层 EXT）
        - base="ext_N" 用 ext_dirs[N]（多层 EXT）
        - 自定义 base 名 → 从 **base_dirs 取对应 key

        对所有 required=True 的声明：加载失败抛 RuntimeError，列出所有错误。
        对所有 required=False 的声明：加载失败静默存空 dict。

        语言包参数化：rules_dir 与当前声明来源不一致时，先按该语言包 tpc.toml
        重新生成声明（_ensure_entries_for）——glob 匹配/文件路径声明都基于当前
        语言包，而非 import 期锁定的默认包。调用方无需先 load_language。
        `enabled` 语义同 `load_language`（None = 包内清单；给定时登记为该包档位）。
        """
        candidate = cls._normalize_pack(rules_dir)
        tier = cls._tier_for_load(candidate, enabled)
        rules_dir = cls._ensure_entries_for(rules_dir, tier)
        cls._active_enabled[candidate] = tier
        decls = [
            (
                name,
                spec.get("file", ""),
                spec.get("section"),
                spec.get("base", "rules"),
                spec.get("required", True),
                spec.get("description", ""),
                spec.get("bare_value"),
            )
            for name, spec in cls._entries.items()
        ]
        cls._loaded, cls._sources = cls._resolve_decls(
            decls, rules_dir, ext_dirs, plugins_dir, base_dirs
        )
        cls._resolved = True

        # 将真实配置值推入各模块的模块级变量
        _push_loaded_config()

    @classmethod
    def resolve(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
        enabled: list[str] | None = None,
        **base_dirs: str,
    ) -> dict:
        """按指定语言包解析配置（**无全局副作用**）。

        与 load_all 不同：不写 _loaded、不改 _entries、不推模块变量。
        供"按语言包自包含解析"的消费方使用——如 Lexer 按自己的 rules_dir
        解析 token/数字形态，不依赖最后一次 load_all 的全局状态（同一进程
        跨语言时不会串用上一语言的配置）。

        `enabled`：**档位**。`None` = 沿用该包"当前档位"（`load_language` 登记过的
        那个；没登记过则用包内清单）——这样 Lexer 之类不需要额外参数就能跟随档位。

        Args:
            rules_dir: 语言包目录（相对项目根，如 "grammar/c4" 或 "c4"）。
        """
        return cls._resolve_cached(
            rules_dir, ext_dirs, plugins_dir, base_dirs, enabled
        )[0]

    @classmethod
    def resolve_with_sources(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
        enabled: list[str] | None = None,
        **base_dirs: str,
    ) -> tuple[dict, dict]:
        """按指定语言包解析配置 + 来源（无全局副作用）。

        与 resolve 相同，但额外返回每个 key 的来源（name → {file, section}
        或 {bare: True}），供调试/可观测（tpc config dump）。`enabled` 语义同 resolve。
        """
        return cls._resolve_cached(
            rules_dir, ext_dirs, plugins_dir, base_dirs, enabled
        )

    @classmethod
    def _resolve_cached(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None,
        plugins_dir: str,
        base_dirs: dict,
        enabled: list[str] | None = None,
    ) -> tuple[dict, dict]:
        """解析语言包配置 → (配置, 来源)，按 (目录, ext, plugins, base, **档位**) 缓存。

        无全局副作用（不写 `_loaded`、不改 `_entries`、不推模块变量）——
        `resolve` / `resolve_with_sources` 共用本函数，只有返回值取用不同。

        ⚠ 缓存键必须含**档位**：同包两档的声明不同，键里没有它就会串档
        （上一轮该功能没生效的第二个根因）。
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate = rules_dir
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            candidate = os.path.join("grammar", rules_dir)
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            # 非语言包目录（临时目录等低层契约）：用当前全局声明
            decls = [
                (
                    name,
                    spec.get("file", ""),
                    spec.get("section"),
                    spec.get("base", "rules"),
                    spec.get("required", True),
                    spec.get("description", ""),
                    spec.get("bare_value"),
                )
                for name, spec in cls._entries.items()
            ]
            tier: tuple[str, ...] = ()
            candidate = rules_dir
        else:
            tier = cls._tier_for_resolve(candidate, enabled)
            decls = _load_meta_declarations(grammar_dir=candidate, enabled=list(tier))
        cache_key = (
            candidate,
            tuple(ext_dirs) if ext_dirs else (),
            plugins_dir,
            frozenset(base_dirs.items()),
            tier,
        )
        if cache_key in cls._resolve_cache:
            return cls._resolve_cache[cache_key]
        result = cls._resolve_decls(decls, candidate, ext_dirs, plugins_dir, base_dirs)
        cls._resolve_cache[cache_key] = result
        return result

    @classmethod
    def _resolve_decls(
        cls,
        decls: list[tuple],
        rules_dir: str,
        ext_dirs: list[str] | None,
        plugins_dir: str,
        base_dirs: dict,
    ) -> tuple[dict, dict]:
        """按声明列表解析配置（纯函数，不写 _loaded）。

        decls: (name, file, section, base, required, description, bare_value) 元组列表。
        供 load_all（用 _entries）与 resolve（用语言包 tpc.toml 声明）共用。

        Returns: (loaded, sources)
            loaded:  name → 配置值
            sources: name → {"file": 实际文件路径, "section": section} 或 {"bare": True}

        分三步：基准目录表（`_build_bases`）→ 逐声明取值（`_load_decl_value`，
        异常按三类分流，fail-fast 语义见各 except 注释）→ 汇总一次性报错。
        """
        bases = cls._build_bases(rules_dir, ext_dirs, plugins_dir, base_dirs)
        loaded: dict[str, Any] = {}
        sources: dict[str, dict] = {}
        errors: list[str] = []

        for name, file_spec, section, base_key, required, _, bare in decls:
            # bare data：非文件式配置，值已由 tpc.toml 直接提供
            if bare is not None:
                loaded[name] = bare
                sources[name] = {"bare": True}
                continue

            base_dir = bases.get(base_key)
            if base_dir is None:
                errors.append(f"  [{name}] base='{base_key}' 未在 load_all() 中提供")
                continue

            try:
                merged, src_files = cls._load_decl_value(
                    file_spec, section, base_dir, required
                )
                loaded[name] = merged
                sources[name] = {
                    "file": src_files[0] if len(src_files) == 1 else src_files,
                    "section": section,
                }
            except tomllib.TOMLDecodeError as e:
                # TOML 语法损坏（重复 key / 格式错误）必须 fail-fast：即使
                # required=False 也不能静默退化成空表——否则下游以空配置继续
                # 运行（如关键字表丢失 → 全部 token 退化为 id），静默错乱。
                loc = cls._decl_loc(base_key, file_spec, section)
                errors.append(f"  [{name}] {loc}: TOML 语法错误: {e}")
            except FileNotFoundError as e:
                # 文件缺失：required=True 是错误；required=False 是合法的可选缺失。
                if required:
                    loc = cls._decl_loc(base_key, file_spec, section)
                    errors.append(f"  [{name}] {loc}: {e}")
                else:
                    loaded[name] = {}
                    sources[name] = {"missing": True, "file": file_spec}
            except Exception as e:
                # 其他异常（缺段/结构不符等）：文件存在但配置结构有问题，属于
                # 配置声明错误——required=False 也不应静默，统一 fail-fast。
                loc = cls._decl_loc(base_key, file_spec, section)
                errors.append(f"  [{name}] {loc}: {e}")
            finally:
                if name not in loaded:
                    loaded[name] = {}
                if name not in sources:
                    sources[name] = {"missing": True, "file": file_spec}

        if errors:
            raise ConfigError(
                "[ConfigRegistry] 以下配置加载失败：\n"
                + "\n".join(errors)
                + "\n\n请检查规则目录结构和 TOML 文件内容。"
            )
        return loaded, sources

    @staticmethod
    def _build_bases(
        rules_dir: str,
        ext_dirs: list[str] | None,
        plugins_dir: str,
        base_dirs: dict,
    ) -> dict[str, str]:
        """基准目录表：rules / ext_N（+ `ext` 别名）/ plugins / 调用方 `base_dirs`。

        调用方键名去掉 `_dir` 后缀便于匹配（`base_dirs` 是 `**kwargs`）。
        """
        bases: dict[str, str] = {"rules": rules_dir}
        ext_list = list(ext_dirs) if ext_dirs else []
        for i, d in enumerate(ext_list):
            bases[f"ext_{i}"] = d
        if ext_list:
            bases["ext"] = ext_list[0]  # 兼容 base="ext"
        else:
            bases["ext"] = ""  # ext 为空，required=False 的声明静默失败
        if plugins_dir:
            bases["plugins"] = plugins_dir
        for bk, bv in base_dirs.items():
            # 去掉 _dir 后缀便于匹配
            key = bk.removesuffix("_dir")
            bases[key] = bv
        return bases

    @staticmethod
    def _decl_loc(base_key: str, file_spec: Any, section: str) -> str:
        """错误定位串：`base:file`（有段声明时再补 ` → [section]`）。"""
        loc = f"{base_key}:{file_spec}"
        if section:
            loc += f" → [{section}]"
        return loc

    @staticmethod
    def _decl_paths(file_spec: Any) -> list[str]:
        """声明 file 字段 → 待展开路径列表（单串或列表；其它类型 → TypeError）。"""
        if isinstance(file_spec, str):
            return [file_spec]
        if isinstance(file_spec, list):
            return file_spec
        raise TypeError(f"file 必须是字符串或列表: {file_spec}")

    @staticmethod
    def _matched_files(fp: str, base_dir: str, required: bool) -> list[str]:
        """单个模式 → 匹配文件列表。

        字面路径即使 glob 不匹配也直接尝试（文件缺失交给 FileNotFoundError）；
        通配符无匹配且必选 → 显式报错（避免 fallback 到含 `*` 的字面路径触发
        Errno 22，以及静默降级为空表）；required=False 的通配无匹配 → 合法空。
        """
        matched = _glob_match([fp], base_dir)
        if matched:
            return matched
        if "*" not in fp and "?" not in fp:
            return [os.path.join(base_dir, fp).replace("\\", "/")]
        if required:
            raise FileNotFoundError(f"glob 未找到匹配文件: {fp}")
        return []

    @staticmethod
    def _read_decl_file(path: str, section: str) -> Any:
        """读单个声明文件 → 数据（有 section 则只取该段）。

        文件存在但缺声明的段 → 配置声明错误，fail-fast（不能再静默
        `data.get(section, {})` 退化成空表）。
        """
        from core.define import FileManager

        content = FileManager.read_file(path.replace("\\", "/"))
        data = tomllib.loads(content)
        if not section:
            return data
        if section not in data:
            raise KeyError(f"文件存在但缺少声明段 [{section}]")
        return data[section]

    @staticmethod
    def _load_decl_value(
        file_spec: Any, section: str, base_dir: str, required: bool
    ) -> tuple[Any, list[str]]:
        """单条声明取值：glob 展开 → 读文件 → 取声明段 → 多文件深合并。

        Returns: (merged, src_files)；无匹配文件 → FileNotFoundError。
        异常分类交给调用方（TOML 语法错 / 文件缺失 / 其它结构错三态）。
        """
        merged: Any = None
        src_files: list[str] = []
        for fp in ConfigRegistry._decl_paths(file_spec):
            for m in sorted(ConfigRegistry._matched_files(fp, base_dir, required)):
                data = ConfigRegistry._read_decl_file(m, section)
                if merged is None:
                    merged = data
                elif isinstance(merged, dict) and isinstance(data, dict):
                    # 深合并：多插件同名配置（token_ext 等嵌套结构）合并，
                    # 浅 update 会让后加载的顶层 key（如 [id]）覆盖前一个。
                    merged = deep_merge(merged, data)
                else:
                    merged = data
                src_files.append(m.replace("\\", "/"))

        if merged is None:
            raise FileNotFoundError(f"未找到匹配文件: {file_spec}")
        return merged, src_files

    @classmethod
    def get(cls, name: str) -> Any:
        """获取已加载的配置值。

        在 load_all() 之前调用抛 RuntimeError（防止隐式依赖）。
        required=False 的声明在加载失败时返回空 dict。
        """
        if not cls._resolved:
            raise RuntimeError(
                f"[ConfigRegistry] get('{name}') 在 load_all() 之前被调用——"
                f"配置尚未加载。请确保管线入口先调用 load_all()。"
            )
        if name not in cls._loaded:
            raise KeyError(
                f"[ConfigRegistry] '{name}' 未声明。可用声明: {list(cls._entries.keys())}"
            )
        return cls._loaded[name]

    @classmethod
    def reset(cls) -> None:
        """重置注册表（测试用）。"""
        cls._entries.clear()
        cls._loaded.clear()
        cls._sources.clear()
        cls._resolved = False
        cls._entries_source = None
        cls._entries_enabled = None
        cls._active_enabled.clear()
        cls._declared_enabled_cache.clear()
        cls._resolve_cache.clear()


# 模块级单例（简化 import）
config = ConfigRegistry

# 自动安装配置声明（在 ConfigRegistry 定义之后，确保 import 安全）
_install_config_declarations()


# ──────────────────────────────────────────────
# 配置声明：declare_cfg(key, default) — 注册 + 取值合一
# ──────────────────────────────────────────────
# 消费端模块级调用一次，自动注册到 _CONFIG_DECLARATIONS，
# 各包 __init__.py 的 get_config_refs() 从此查询，无需源码扫描。

_CONFIG_DECLARATIONS: dict[str, list[tuple[str, str]]] = {}
"""{ "namespace.key": [("module.name", "_var_cfg"), ...], ... }"""


T = TypeVar("T")


def declare_cfg(key: str, default: T, module: str = "", var: str = "") -> T:
    """声明一个配置依赖：注册 key 并返回默认值。

    load_all() 完成后会推入真实配置值，此后代码只通过变量使用。
    同一 key 可被多个模块声明，每个都会收到推送。

    若配置已加载（_resolved），直接返回真实值——支持 load_language 之后
    按需 import 消费模块（否则该模块的 declare_cfg 注册晚于 _push_loaded_config，
    会一直持有默认值）。

    用法:
        _xxx_cfg = declare_cfg("namespace.key", {default}, __name__, "_xxx_cfg")
    """
    if module and var:
        _CONFIG_DECLARATIONS.setdefault(key, []).append((module, var))
    if ConfigRegistry._resolved:
        return ConfigRegistry._loaded.get(key, default)
    return default


def config_refs_for(prefix: str) -> dict[str, str]:
    """按模块名前缀取配置需求表：{ "namespace.key": "_xxx_cfg", ... }。

    各部件 `__init__.py` 的 `get_config_refs()` 是对本函数的薄包装
    （前缀 = 包名，如 `lexer` / `parser`）——扫描逻辑只有一份，
    新增部件不再拷表达式。
    """
    scope = prefix + "."
    return {
        key: var
        for key, entries in _CONFIG_DECLARATIONS.items()
        for mod, var in entries
        if mod.startswith(scope)
    }


def _push_loaded_config() -> None:
    """load_all() 完成后调用，将真实配置值推入各模块的模块级变量。"""
    import sys

    for key, entries in _CONFIG_DECLARATIONS.items():
        for mod_name, var_name in entries:
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            try:
                val = config.get(key)
                setattr(mod, var_name, val)
            except (KeyError, RuntimeError):
                # 声明制契约：语言包未声明该键（KeyError）→ 保留模块默认值；
                # 未 load_all（RuntimeError）同理。两者都是"无配置"的正常情形。
                pass
