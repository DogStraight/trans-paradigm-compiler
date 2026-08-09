"""component_loader.py — Component loading and management.

A component is a self-contained unit of grammar rules + analyzer primitives
+ transform slots, located in grammar/<lang>/plugins/<name>/.
"""

import importlib.util
import os
import sys
from typing import Any, Callable

from core._protocol import META_NAME, META_REQUIRES

def _get_component_dir() -> str:
    """Resolve component directory: grammar/<lang>/plugins/."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        from core.define import DEFAULT_RULES_DIR
        plugins_dir = os.path.join(root, DEFAULT_RULES_DIR, "plugins")
        if os.path.isdir(plugins_dir):
            return plugins_dir
    except Exception:
        pass
    return ""

_loaded_components: dict[str, dict[str, Any]] = {}
_transform_slots: dict[str, Callable] = {}
_PRIMITIVE_ORDER: list[str] = []


def discover_components() -> list[dict[str, Any]]:
    """Scan plugins/ directories for tpc.toml with [component] section."""
    comp_dir = _get_component_dir()
    if not comp_dir or not os.path.isdir(comp_dir):
        return []
    result = []
    for name in sorted(os.listdir(comp_dir)):
        cdir = os.path.join(comp_dir, name)
        if not os.path.isdir(cdir) or name.startswith("_"):
            continue
        toml_path = os.path.join(cdir, "tpc.toml")
        if not os.path.isfile(toml_path):
            continue
        meta = _parse_component_toml(toml_path)
        if meta:
            meta["_dir"] = cdir
            result.append(meta)
    return result


def _parse_component_toml(path: str) -> dict[str, Any] | None:
    """Parse plugin tpc.toml's [grammar]/[analyzer]/[transform] sections."""
    import tomllib

    with open(path, "rb") as f:
        raw = tomllib.load(f)
    # Require at least [grammar] files to be a valid component
    grammar = raw.get("grammar", {})
    if not grammar.get("files"):
        return None
    comp = {
        "name": os.path.basename(os.path.dirname(path)),
        "grammar": grammar,
        "analyzer": raw.get("analyzer", {}),
        "transform": raw.get("transform", {}),
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

    # 3. Transform handlers
    transform_meta = meta.get("transform", {})
    info["transform"] = _load_python_handlers(cdir, transform_meta.get("handlers", []))

    _loaded_components[name] = info
    return info


def load_all_components() -> list[dict[str, Any]]:
    """Discover, dependency-sort, and load all components."""
    metas = discover_components()
    ordered = _resolve_dependencies(metas)
    result = []
    for meta in ordered:
        info = load_component(meta)
        result.append(info)
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


def get_component_mapping_config() -> tuple[dict, dict]:
    """Collect mapping_entries and resolve_entries from all loaded components."""
    mapping_entries: dict = {}
    resolve_entries: dict = {}
    for info in _loaded_components.values():
        for mod in info.get("analyzer", []):
            entries = getattr(mod, "mapping_entries", None)
            if entries:
                mapping_entries.update(entries)
            resolves = getattr(mod, "resolve_entries", None)
            if resolves:
                resolve_entries.update(resolves)
    return mapping_entries, resolve_entries


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


def _load_python_handlers(cdir: str, handler_files: list[str]) -> list[Any]:
    """Load Python handler files from a component directory."""
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



