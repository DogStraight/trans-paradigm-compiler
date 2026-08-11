"""ConfigRegistry — 声明式配置注册中心。

用法:
    # 1. 在管线启动点统一加载
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all(rules_dir, ext_dirs=ext_dirs)

    # 2. 使用（key 为 "lexer.xxx" / "pratt.xxx" / "renderer.xxx" 等）
    cats = config.get("parser.token_categories")

配置声明自动从 grammar 包的 tpc.toml 中读取 [xxx] 注册（grammar 段落除外）。

Doc: docs/decisions/0003-config-load-fail-fast.md
"""

import os
import json
import re
import tomllib
from typing import Any, TypeVar

from core.errors import ConfigError

_CONFIG_CANDIDATES = ["config/tpc_config.json"]


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


def _find_user_config() -> str:
    """Find project config file (duplicated in define.py to avoid circular imports)."""
    env_path = os.environ.get("TPC_CONFIG")
    if env_path:
        path = os.path.abspath(env_path)
        if os.path.isfile(path):
            return path
    cwd = os.path.abspath(os.getcwd())
    parent = cwd
    while True:
        for name in _CONFIG_CANDIDATES:
            path = os.path.join(parent, name)
            if os.path.isfile(path):
                return path
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent
    return ""


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
    meta_path = os.path.join(root, grammar_dir, "tpc.toml")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"[config] Grammar package tpc.toml not found: {meta_path}"
        )
    return meta_path


def _flatten_config(table: dict, prefix: str = "") -> list:
    """Recursively flatten nested config table into (dotted_key, spec) pairs."""
    result = []
    for key, value in table.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "file" not in value:
            result.extend(_flatten_config(value, full_key))
        else:
            result.append((full_key, value))
    return result


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
                plugin_tpc = os.path.join(package_dir, "plugins", name, "tpc.toml")
                if not os.path.isfile(plugin_tpc):
                    continue
                with open(plugin_tpc, encoding="utf-8") as f:
                    plugin_meta = tomllib.loads(f.read())
                for ns, table in plugin_meta.items():
                    if ns == "grammar":
                        continue
                    for config_key, spec in _flatten_config({ns: table}):
                        if isinstance(spec, dict) and isinstance(
                            spec.get("file"), (str, list)
                        ):
                            file_spec = spec["file"]
                            prefixed = file_spec
                            if isinstance(file_spec, str):
                                prefixed = f"{name}/{file_spec}"
                            elif isinstance(file_spec, list):
                                prefixed = [f"{name}/{f}" for f in file_spec]
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
    def load_language(
        cls,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        plugins_dir: str = "",
    ) -> None:
        """加载指定语言包（**单语言选择**）：从 rules_dir 的 tpc.toml 重新生成
        配置声明并加载全部配置。

        架构约束（2026-08-12 决策）：
        - 管线**一次只使用一种语言的语法**——本方法在初始化时选一个语言包
          （c4 或 verilog），加载后替换全部声明，不与其他语言混合共存。
        - **非运行中热重载**：语言切换 = 重新初始化管线（改 config 指向 +
          重启，或测试/验证时显式 load_language），不提供热切换 API。
        - 默认 import 期只从 config/tpc_config.json 指向的单一 grammar 包注册
          声明（单语言假设）；本方法供第二语言（c4 等）验证时选择语言包。

        Args:
            rules_dir: 语言包目录（相对项目根，如 "grammar/c4" 或 "c4"）。
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isfile(os.path.join(root, rules_dir, "tpc.toml")):
            rules_dir = os.path.join("grammar", rules_dir)
        if not os.path.isfile(os.path.join(root, rules_dir, "tpc.toml")):
            raise ConfigError(
                f"[config] grammar package tpc.toml not found under: {rules_dir}"
            )
        decls = _load_meta_declarations(grammar_dir=rules_dir)
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

        cls._loaded.clear()
        errors: list[str] = []

        for name, spec in cls._entries.items():
            # bare data：非文件式配置，值已由 tpc.toml 直接提供
            bare = spec.get("bare_value")
            if bare is not None:
                cls._loaded[name] = bare
                continue

            base_key = spec.get("base", "rules")
            base_dir = bases.get(base_key)
            if base_dir is None:
                errors.append(f"  [{name}] base='{base_key}' 未在 load_all() 中提供")
                continue

            try:
                file_spec = spec["file"]
                # file 可以是字符串（单文件）或列表（glob 模式）
                if isinstance(file_spec, str):
                    paths = [file_spec]
                elif isinstance(file_spec, list):
                    paths = file_spec
                else:
                    raise TypeError(f"file 必须是字符串或列表: {file_spec}")

                merged: Any = None
                for fp in paths:
                    # glob 模式：匹配 0 或多个文件
                    matched = _glob_match([fp], base_dir)
                    if not matched:
                        if "*" not in fp and "?" not in fp:
                            # 字面路径：glob 不匹配也直接尝试（文件缺失交给 FileNotFoundError）
                            matched = [os.path.join(base_dir, fp).replace("\\", "/")]
                        elif spec["required"]:
                            # 通配符无匹配且必选 → 显式报错。避免 fallback 到含 * 的
                            # 字面路径触发 Errno 22，以及静默降级为空表。
                            raise FileNotFoundError(f"glob 未找到匹配文件: {fp}")
                        # required=False 的通配无匹配 → 合法空（跳过）
                    for m in sorted(matched):
                        content = FileManager.read_file(m.replace("\\", "/"))
                        data = tomllib.loads(content)
                        if spec["section"]:
                            # 文件存在但缺声明的段 → 配置声明错误，fail-fast
                            # （不能再静默 `data.get(section, {})` 退化成空表）。
                            if spec["section"] not in data:
                                raise KeyError(
                                    f"文件存在但缺少声明段 [{spec['section']}]"
                                )
                            data = data[spec["section"]]
                        if merged is None:
                            merged = data
                        elif isinstance(merged, dict) and isinstance(data, dict):
                            merged.update(data)
                        else:
                            merged = data

                if merged is None:
                    raise FileNotFoundError(f"未找到匹配文件: {file_spec}")
                cls._loaded[name] = merged

            except tomllib.TOMLDecodeError as e:
                # TOML 语法损坏（重复 key / 格式错误）必须 fail-fast：即使
                # required=False 也不能静默退化成空表——否则下游以空配置继续
                # 运行（如关键字表丢失 → 全部 token 退化为 id），静默错乱。
                loc = f"{base_key}:{spec['file']}"
                if spec["section"]:
                    loc += f" → [{spec['section']}]"
                errors.append(f"  [{name}] {loc}: TOML 语法错误: {e}")
            except FileNotFoundError as e:
                # 文件缺失：required=True 是错误；required=False 是合法的可选缺失。
                if spec["required"]:
                    loc = f"{base_key}:{spec['file']}"
                    if spec["section"]:
                        loc += f" → [{spec['section']}]"
                    errors.append(f"  [{name}] {loc}: {e}")
                else:
                    cls._loaded[name] = {}
            except Exception as e:
                # 其他异常（缺段/结构不符等）：文件存在但配置结构有问题，属于
                # 配置声明错误——required=False 也不应静默，统一 fail-fast。
                loc = f"{base_key}:{spec['file']}"
                if spec["section"]:
                    loc += f" → [{spec['section']}]"
                errors.append(f"  [{name}] {loc}: {e}")
            finally:
                if name not in cls._loaded:
                    cls._loaded[name] = {}

        if errors:
            raise ConfigError(
                "[ConfigRegistry] 以下配置加载失败：\n"
                + "\n".join(errors)
                + "\n\n请检查规则目录结构和 TOML 文件内容。"
            )

        cls._resolved = True

        # 将真实配置值推入各模块的模块级变量
        _push_loaded_config()

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
        cls._resolved = False


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
