"""
component_loader.py — 组件加载器

组件 = 语法规则 + 分析器原语 + 变换槽位的自包含单元。
每个组件在 grammar/rules_verilog_ext/_components/<name>/ 目录中。
"""

import importlib.util
import os
import sys
from typing import Any

_COMPONENT_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "grammar", "rules_verilog_ext", "_components",
)

# 全局注册：组件名 → { grammar, analyzer, transform }
_loaded_components: dict[str, dict[str, Any]] = {}


def discover_components() -> list[dict[str, Any]]:
    """扫描 _components/ 目录，返回所有组件元信息。"""
    if not os.path.isdir(_COMPONENT_DIR):
        return []
    result = []
    for name in sorted(os.listdir(_COMPONENT_DIR)):
        cdir = os.path.join(_COMPONENT_DIR, name)
        if not os.path.isdir(cdir):
            continue
        toml_path = os.path.join(cdir, "component.toml")
        if not os.path.isfile(toml_path):
            continue
        meta = _parse_component_toml(toml_path)
        if meta:
            meta["_dir"] = cdir
            result.append(meta)
    return result


def _parse_component_toml(path: str) -> dict[str, Any] | None:
    """简易解析 component.toml（仅支持单层 [table]）。"""
    import tomllib
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    comp = raw.get("component", {})
    if not comp.get("name"):
        return None
    return comp


def load_component(meta: dict[str, Any]) -> dict[str, Any]:
    """加载一个组件：grammar → analyzer → transform。"""
    name = meta["name"]
    if name in _loaded_components:
        return _loaded_components[name]

    cdir = meta["_dir"]
    info: dict[str, Any] = {"name": name, "meta": meta}

    # 1. 语法文件（组件本地 grammar files）
    grammar_meta = meta.get("grammar", {})
    grammar_files = grammar_meta.get("files", [])
    loaded_grammars = []
    for fname in grammar_files:
        fpath = os.path.join(cdir, fname)
        if os.path.isfile(fpath):
            loaded_grammars.append(fpath)
    info["grammar_files"] = loaded_grammars

    # 2. 分析器 handler
    analyzer_handlers = meta.get("analyzer", {})
    info["analyzer"] = _load_python_handlers(cdir, analyzer_handlers.get("handlers", []))

    # 3. 变换 handler
    transform_meta = meta.get("transform", {})
    info["transform"] = _load_python_handlers(cdir, transform_meta.get("handlers", []))

    _loaded_components[name] = info
    return info


# 全局变换槽位注册表
_transform_slots: dict[str, callable] = {}


def register_transform_slot(name: str):
    """装饰器：注册变换槽位。"""
    def decorator(fn):
        _transform_slots[name] = fn
        return fn
    return decorator


def get_transform_slots() -> dict[str, callable]:
    return dict(_transform_slots)


def _load_python_handlers(cdir: str, handler_files: list[str]) -> list[Any]:
    """加载组件中的 Python handler 文件。"""
    modules = []
    for hf in handler_files:
        hpath = os.path.join(cdir, hf)
        if not os.path.isfile(hpath):
            continue
        mod_name = f"_comp_{os.path.basename(cdir)}_{hf.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, hpath)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            modules.append(mod)
    return modules


def load_all_components() -> list[dict[str, Any]]:
    """发现并加载所有组件。"""
    result = []
    for meta in discover_components():
        info = load_component(meta)
        result.append(info)
    return result


def get_component_grammar_files() -> list[str]:
    """获取所有组件的语法文件路径列表。"""
    files = []
    for info in _loaded_components.values():
        files.extend(info.get("grammar_files", []))
    return files


def get_loaded_components() -> dict[str, dict[str, Any]]:
    return dict(_loaded_components)
