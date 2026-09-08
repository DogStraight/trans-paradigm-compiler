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
    """
    compiled = [_glob_to_regex(p) for p in patterns]
    # 统一分隔符后再用 os.sep 判断，跨平台兼容
    has_dir = any(os.sep in p.replace("/", os.sep) for p in patterns)
    results: list[str] = []

    if not has_dir:
        try:
            for entry in os.scandir(base_dir):
                if entry.is_file():
                    for regex in compiled:
                        if regex.match(entry.name):
                            results.append(entry.path)
                            break
        except PermissionError:
            pass
        return sorted(results)

    try:
        for root, dirs, files in os.walk(base_dir):
            rel_root = os.path.relpath(root, base_dir)
            if rel_root == ".":
                rel_root = ""
            for name in files + dirs:
                rel_path = os.path.join(rel_root, name)
                for regex in compiled:
                    if regex.match(rel_path):
                        results.append(os.path.join(root, name))
                        break
    except PermissionError:
        pass

    return sorted(results)


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
            g = cfg.get("grammar", "")
            grammar_dir = g if isinstance(g, str) else g.get("rules_dir", "")
        except (json.JSONDecodeError, KeyError):
            pass
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


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 到 base（dict 嵌套合并，非 dict 值后者优先）。

    用于同名配置 key 的多来源合并（多插件 token_ext 等）：浅 update 会让
    后加载的顶层 key（如 [id]）整体覆盖前一个，深合并保留嵌套结构。
    """
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


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
        f = spec["file"]
        if isinstance(f, str):
            pass
        elif isinstance(f, list) and all(isinstance(x, str) for x in f):
            pass
        else:
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
    else:
        # dict 但无 file：若含声明字段（section/required/base/description）则
        # 疑似"忘了 file 的文件式声明"——拦截；纯数据 dict 是合法 bare data。
        decl_like = set(spec) & {"section", "required", "base", "description"}
        if decl_like:
            raise ConfigError(
                f"[config] {config_key}: 疑似文件式声明但缺 file 字段"
                f"（含 {sorted(decl_like)}）。文件式声明需 file = \"...\"。"
            )


def _find_plugin_tpc(package_dir: str, name: str) -> tuple[str, str]:
    """在 plugins/ 目录树递归查找组件 <name>/tpc.toml（聚类目录支持）。

    返回 (tpc 绝对路径, 相对 plugins/ 的目录路径，如 "name" 或 "checks/name")。
    未找到返回 ("", "")——enabled 列表引用未安装组件时静默跳过（与平铺时代
    行为一致：组件缺失不阻断配置声明收集）。
    """
    plugins_dir = os.path.join(package_dir, "plugins")
    if not os.path.isdir(plugins_dir):
        return "", ""
    for root, dirs, files in os.walk(plugins_dir):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        if os.path.basename(root) != name or "tpc.toml" not in files:
            continue
        rel = os.path.relpath(root, plugins_dir).replace("\\", "/")
        return os.path.join(root, "tpc.toml"), rel
    return "", ""


def _load_meta_declarations(grammar_dir: str = "") -> list[tuple]:
    """Read [config.*] declarations from grammar package tpc.toml files.

    Args:
        grammar_dir: 语言包目录（相对项目根，如 "grammar/c4"）。空时用
            默认包（config/tpc_config.json 指向的 grammar）——保持既有单语言
            行为；第二语言（c4 等）通过 ConfigRegistry.load_language 传入。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    declarations = []

    # 1. Core grammar package — 所有 [xxx] 段落（除了 grammar）都是配置声明
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
    for ns, table in meta.items():
        if ns == "grammar":
            continue
        for config_key, spec in _flatten_config({ns: table}):
            _validate_decl_spec(config_key, spec)
            if isinstance(spec, dict) and isinstance(spec.get("file"), (str, list)):
                # 文件式配置：file 为字符串路径或列表模式
                declarations.append(
                    (
                        config_key,
                        spec.get("file", ""),
                        spec.get("section"),
                        spec.get("base", "rules"),
                        spec.get("required", True),
                        spec.get("description", ""),
                        None,
                    )
                )
            else:
                # 非文件式配置，以 bare data 形式注册
                declarations.append((config_key, "", None, "", False, "", spec))

    # 2. Plugin packages — 从 [plugins] enabled 读取插件 tpc.toml
    plugins_cfg = meta.get("plugins", {})
    if isinstance(plugins_cfg, dict):
        enabled = plugins_cfg.get("enabled", [])
        if isinstance(enabled, list):
            package_dir = os.path.dirname(core_path)
            for name in enabled:
                plugin_tpc, rel_dir = _find_plugin_tpc(package_dir, name)
                if not plugin_tpc:
                    continue
                with open(plugin_tpc, encoding="utf-8") as f:
                    plugin_meta = tomllib.loads(f.read())
                for ns, table in plugin_meta.items():
                    if ns == "grammar":
                        continue
                    for config_key, spec in _flatten_config({ns: table}):
                        _validate_decl_spec(config_key, spec)
                        if isinstance(spec, dict) and isinstance(
                            spec.get("file"), (str, list)
                        ):
                            file_spec = spec["file"]
                            prefixed = file_spec
                            if isinstance(file_spec, str):
                                prefixed = f"{rel_dir}/{file_spec}"
                            elif isinstance(file_spec, list):
                                prefixed = [f"{rel_dir}/{f}" for f in file_spec]
                            # 同名配置 key 合并（多插件 token_ext 等共存）：若已有同
                            # config_key 的插件声明，file 并入列表——否则扁平同名 key
                            # 后加载覆盖先加载，只保留一个插件来源（resolve 语义）。
                            merged_idx = None
                            for i, d in enumerate(declarations):
                                if d[0] == config_key and d[3] == "plugins":
                                    merged_idx = i
                                    break
                            if merged_idx is not None:
                                old = declarations[merged_idx]
                                old_files = old[1]
                                if isinstance(old_files, str):
                                    old_files = [old_files]
                                new_files = old_files + (
                                    [prefixed] if isinstance(prefixed, str) else prefixed
                                )
                                declarations[merged_idx] = (
                                    config_key,
                                    new_files,
                                    old[2],
                                    "plugins",
                                    old[4],
                                    old[5],
                                    None,
                                )
                            else:
                                declarations.append(
                                    (
                                        config_key,
                                        prefixed,
                                        spec.get("section"),
                                        "plugins",
                                        spec.get("required", False),
                                        spec.get("description", ""),
                                        None,
                                    )
                                )
                        else:
                            # 非文件式配置（bare data）——插件 tpc.toml 里也可能有
                            # 裸配置（[namespace].foo 点路径键，如插件自身的开关项）。
                            # 缺此分支会导致插件裸配置从未注册（历史 bug）。
                            declarations.append(
                                (config_key, "", None, "", False, "", spec)
                            )
    return declarations


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

    @classmethod
    def _ensure_entries_for(cls, rules_dir: str) -> str:
        """确保 _entries 声明来自指定语言包，返回规范化 rules_dir。

        若 rules_dir 存在 tpc.toml（语言包目录）且当前 _entries 来源不是该
        语言包，按该语言包 tpc.toml 重新生成声明——glob 匹配/文件路径声明
        都基于当前语言包，而非 import 期锁定的默认包。
        若 rules_dir 无 tpc.toml（临时目录等低层用法），保持现有 _entries
        不变（load_all 只换 base 目录），兼容直接 declare + load_all 的契约。
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate = rules_dir
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            candidate = os.path.join("grammar", rules_dir)
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            return rules_dir  # 非语言包目录：保持现有声明（低层契约）
        if cls._entries_source != candidate:
            decls = _load_meta_declarations(grammar_dir=candidate)
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
        return candidate

    @classmethod
    def load_language(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
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
        """
        rules_dir = cls._ensure_entries_for(rules_dir)
        cls.load_all(rules_dir, ext_dirs=ext_dirs, plugins_dir=plugins_dir)

    @classmethod
    def load_all(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
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
        """
        rules_dir = cls._ensure_entries_for(rules_dir)
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
        **base_dirs: str,
    ) -> dict:
        """按指定语言包解析配置（**无全局副作用**）。

        与 load_all 不同：不写 _loaded、不改 _entries、不推模块变量。
        供"按语言包自包含解析"的消费方使用——如 Lexer 按自己的 rules_dir
        解析 token/数字形态，不依赖最后一次 load_all 的全局状态（同一进程
        跨语言时不会串用上一语言的配置）。

        Args:
            rules_dir: 语言包目录（相对项目根，如 "grammar/c4" 或 "c4"）。
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
            candidate = rules_dir
        else:
            decls = _load_meta_declarations(grammar_dir=candidate)
        cache_key = (
            candidate,
            tuple(ext_dirs) if ext_dirs else (),
            plugins_dir,
            frozenset(base_dirs.items()),
        )
        if cache_key in cls._resolve_cache:
            return cls._resolve_cache[cache_key][0]
        result, sources = cls._resolve_decls(
            decls, candidate, ext_dirs, plugins_dir, base_dirs
        )
        cls._resolve_cache[cache_key] = (result, sources)
        return result

    @classmethod
    def resolve_with_sources(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
        **base_dirs: str,
    ) -> tuple[dict, dict]:
        """按指定语言包解析配置 + 来源（无全局副作用）。

        与 resolve 相同，但额外返回每个 key 的来源（name → {file, section}
        或 {bare: True}），供调试/可观测（tpc config dump）。
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate = rules_dir
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
            candidate = os.path.join("grammar", rules_dir)
        if not os.path.isfile(os.path.join(root, candidate, "tpc.toml")):
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
            candidate = rules_dir
        else:
            decls = _load_meta_declarations(grammar_dir=candidate)
        cache_key = (
            candidate,
            tuple(ext_dirs) if ext_dirs else (),
            plugins_dir,
            frozenset(base_dirs.items()),
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
        """
        from core.define import FileManager

        # 基准目录表
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
                # file 可以是字符串（单文件）或列表（glob 模式）
                if isinstance(file_spec, str):
                    paths = [file_spec]
                elif isinstance(file_spec, list):
                    paths = file_spec
                else:
                    raise TypeError(f"file 必须是字符串或列表: {file_spec}")

                merged: Any = None
                src_files: list[str] = []
                for fp in paths:
                    # glob 模式：匹配 0 或多个文件
                    matched = _glob_match([fp], base_dir)
                    if not matched:
                        if "*" not in fp and "?" not in fp:
                            # 字面路径：glob 不匹配也直接尝试（文件缺失交给 FileNotFoundError）
                            matched = [os.path.join(base_dir, fp).replace("\\", "/")]
                        elif required:
                            # 通配符无匹配且必选 → 显式报错。避免 fallback 到含 * 的
                            # 字面路径触发 Errno 22，以及静默降级为空表。
                            raise FileNotFoundError(f"glob 未找到匹配文件: {fp}")
                        # required=False 的通配无匹配 → 合法空（跳过）
                    for m in sorted(matched):
                        content = FileManager.read_file(m.replace("\\", "/"))
                        data = tomllib.loads(content)
                        if section:
                            # 文件存在但缺声明的段 → 配置声明错误，fail-fast
                            # （不能再静默 `data.get(section, {})` 退化成空表）。
                            if section not in data:
                                raise KeyError(f"文件存在但缺少声明段 [{section}]")
                            data = data[section]
                        if merged is None:
                            merged = data
                        elif isinstance(merged, dict) and isinstance(data, dict):
                            # 深合并：多插件同名配置（token_ext 等嵌套结构）合并，
                            # 浅 update 会让后加载的顶层 key（如 [id]）覆盖前一个。
                            merged = _deep_merge(merged, data)
                        else:
                            merged = data
                        src_files.append(m.replace("\\", "/"))

                if merged is None:
                    raise FileNotFoundError(f"未找到匹配文件: {file_spec}")
                loaded[name] = merged
                sources[name] = {
                    "file": src_files[0] if len(src_files) == 1 else src_files,
                    "section": section,
                }

            except tomllib.TOMLDecodeError as e:
                # TOML 语法损坏（重复 key / 格式错误）必须 fail-fast：即使
                # required=False 也不能静默退化成空表——否则下游以空配置继续
                # 运行（如关键字表丢失 → 全部 token 退化为 id），静默错乱。
                loc = f"{base_key}:{file_spec}"
                if section:
                    loc += f" → [{section}]"
                errors.append(f"  [{name}] {loc}: TOML 语法错误: {e}")
            except FileNotFoundError as e:
                # 文件缺失：required=True 是错误；required=False 是合法的可选缺失。
                if required:
                    loc = f"{base_key}:{file_spec}"
                    if section:
                        loc += f" → [{section}]"
                    errors.append(f"  [{name}] {loc}: {e}")
                else:
                    loaded[name] = {}
                    sources[name] = {"missing": True, "file": file_spec}
            except Exception as e:
                # 其他异常（缺段/结构不符等）：文件存在但配置结构有问题，属于
                # 配置声明错误——required=False 也不应静默，统一 fail-fast。
                loc = f"{base_key}:{file_spec}"
                if section:
                    loc += f" → [{section}]"
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
                pass
