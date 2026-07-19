"""ConfigRegistry — 声明式配置注册中心。

用法:
    # 1. 在管线启动点统一加载
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all(rules_dir, ext_dirs=ext_dirs)

    # 2. 使用（key 为 "lexer.xxx" / "pratt.xxx" / "renderer.xxx" 等）
    cats = config.get("parser.token_categories")

配置声明自动从 grammar 包的 pyv.toml 中读取 [xxx] 注册（grammar 段落除外）。
"""

import json
import os
import tomllib
from typing import Any, TypeVar

_CONFIG_CANDIDATES = ["config/pyv_config.json"]


# ──────────────────────────────────────────────
# 配置声明加载（从 grammar 包 pyv.toml 读取 [config.*]）
# ──────────────────────────────────────────────


def _find_user_config() -> str:
    """Find project config file (duplicated in define.py to avoid circular imports)."""
    env_path = os.environ.get("PYV_CONFIG")
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


def _find_grammar_pyv_toml() -> str:
    """Locate the grammar package's pyv.toml."""
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
    meta_path = os.path.join(root, grammar_dir, "pyv.toml")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"[config] Grammar package pyv.toml not found: {meta_path}"
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


def _load_meta_declarations() -> list[tuple]:
    """Read [config.*] declarations from grammar package pyv.toml files."""
    declarations = []

    # 1. Core grammar package — 所有 [xxx] 段落（除了 grammar）都是配置声明
    core_path = _find_grammar_pyv_toml()
    with open(core_path, encoding="utf-8") as f:
        meta = tomllib.loads(f.read())
    for ns, table in meta.items():
        if ns == "grammar":
            continue
        for config_key, spec in _flatten_config({ns: table}):
            declarations.append((
                config_key,
                spec.get("file", ""),
                spec.get("section"),
                spec.get("base", "rules"),
                spec.get("required", True),
                spec.get("description", ""),
            ))

    # 2. EXT grammar packages (auto-discover: <grammar_dir>/ext/pyv.toml)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core_pyv = _find_grammar_pyv_toml()
    grammar_dir = os.path.dirname(core_pyv)
    ext_dirs = []
    ext_candidate = os.path.join(grammar_dir, "ext", "pyv.toml")
    if os.path.isfile(ext_candidate):
        ext_dirs.append(os.path.join(grammar_dir, "ext"))
    for i, ed in enumerate(ext_dirs):
        ext_pyv = os.path.join(root, ed, "pyv.toml")
        if not os.path.isfile(ext_pyv):
            continue
        with open(ext_pyv, encoding="utf-8") as f:
            ext_meta = tomllib.loads(f.read())
        for ns, table in ext_meta.items():
            if ns == "grammar":
                continue
            for config_key, spec in _flatten_config({ns: table}):
                declarations.append((
                    config_key,
                    spec.get("file", ""),
                    spec.get("section"),
                    spec.get("base", f"ext_{i}"),
                    spec.get("required", False),
                    spec.get("description", ""),
                ))
    return declarations


_DECLARATIONS = _load_meta_declarations()


def _install_config_declarations():
    """注册所有配置声明（模块导入时自动执行）。"""
    for name, file, section, base, required, desc in _DECLARATIONS:
        config.declare(
            name,
            file=file,
            section=section,
            base=base,
            required=required,
            description=desc,
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
        file: str,
        section: str | None = None,
        required: bool = True,
        base: str = "rules",
        description: str = "",
    ) -> None:
        """声明一个配置依赖。

        Args:
            name: 配置唯一标识名（命名空间风格，如 "pratt.token_categories"）
            file: TOML 文件路径（相对 base 目录）
            section: TOML 中的 section key，None 表示整个文件内容
            required: 加载失败是否致命（True=崩溃，False=静默返回空 dict）
            base: 基准目录名，对应 load_all() 的 **base_dirs 参数中的 key
            description: 人类可读描述（用于错误信息）
        """
        if name in cls._entries:
            return  # 重复声明安全无害
        cls._entries[name] = {
            "file": file,
            "section": section,
            "required": required,
            "base": base,
            "description": description,
        }

    @classmethod
    def load_all(
        cls, rules_dir: str, ext_dirs: list[str] | None = None, **base_dirs: str
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
        for bk, bv in base_dirs.items():
            # 去掉 _dir 后缀便于匹配
            key = bk.removesuffix("_dir")
            bases[key] = bv

        cls._loaded.clear()
        errors: list[str] = []

        for name, spec in cls._entries.items():
            base_key = spec.get("base", "rules")
            base_dir = bases.get(base_key)
            if base_dir is None:
                errors.append(f"  [{name}] base='{base_key}' 未在 load_all() 中提供")
                continue

            try:
                path = os.path.join(base_dir, spec["file"]).replace("\\", "/")
                content = FileManager.read_file(path)
                data = tomllib.loads(content)

                if spec["section"]:
                    data = data.get(spec["section"], {})

                cls._loaded[name] = data

            except Exception as e:
                if spec["required"]:
                    loc = f"{base_key}:{spec['file']}"
                    if spec["section"]:
                        loc += f" → [{spec['section']}]"
                    errors.append(f"  [{name}] {loc}: {e}")
                else:
                    cls._loaded[name] = {}

        if errors:
            raise RuntimeError(
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
    用法:
        _xxx_cfg = declare_cfg("namespace.key", {default}, __name__, "_xxx_cfg")
    """
    if module and var:
        _CONFIG_DECLARATIONS.setdefault(key, []).append((module, var))
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
