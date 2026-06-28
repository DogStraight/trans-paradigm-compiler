"""
config_loader.py — 加载 Transform 配置

从三处来源加载：
    1. 语法规则的 [RuleName.transform] 块（规则自身声明）
    2. 增强目录 _manifest.toml 中引用的类型表
    3. 增强规则自身的 [RuleName.transform] 块
"""

import os
import tomllib
from typing import Any, Optional


def load_rules_transform_configs(
    rules: dict[str, Any],
) -> dict[str, dict]:
    """从 GrammarRule 对象中提取 transform 配置

    遍历所有规则，收集具有 .transform 属性的规则。
    transform 属性是 dict 格式（来自 TOML 的 [RuleName.transform]）。

    Returns:
        { rule_name: transform_dict, ... }
        例如: { "TypedPortDecl": {"kind": "expand", "source": {...}} }
    """
    configs: dict[str, dict] = {}
    for name, rule in rules.items():
        transform = getattr(rule, "transform", None)
        if isinstance(transform, dict):
            configs[name] = transform
    return configs


def load_type_tables(ext_dir: str) -> dict[str, Any]:
    """从增强目录加载类型参考表

    加载 _manifest.toml 中 types 字段指向的文件，
    以及 ext 目录下所有 _types.toml。

    Returns:
        { "type": { "spi": { "master": {...}, ... } }, ... }
    """
    tables: dict[str, Any] = {}

    if not os.path.isdir(ext_dir):
        return tables

    # 1. 读取 _manifest.toml
    manifest_path = os.path.join(ext_dir, "_manifest.toml")
    if os.path.isfile(manifest_path):
        with open(manifest_path, "rb") as f:
            manifest = tomllib.load(f)
        ext_cfg = manifest.get("ext", {})
        types_file = ext_cfg.get("types", "")
        if types_file:
            types_path = os.path.join(ext_dir, types_file)
            if os.path.isfile(types_path):
                with open(types_path, "rb") as f:
                    types_data = tomllib.load(f)
                _organize_tables(types_data, tables)

    # 2. 扫描所有 _types.toml
    for fname in sorted(os.listdir(ext_dir)):
        if fname.startswith("_") and fname.endswith("_types.toml"):
            fpath = os.path.join(ext_dir, fname)
            if fpath == manifest_path:
                continue
            with open(fpath, "rb") as f:
                types_data = tomllib.load(f)
            _organize_tables(types_data, tables)

    return tables


def _organize_tables(flat: dict, tables: dict) -> None:
    """将扁平 TOML key（如 type.spi.master）组织为嵌套 dict"""
    for key, value in flat.items():
        parts = key.split(".")
        target = tables
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        # 避免覆盖已有子表
        last_key = parts[-1]
        if (
            last_key in target
            and isinstance(target[last_key], dict)
            and isinstance(value, dict)
        ):
            target[last_key].update(value)
        else:
            target[last_key] = value


def load_transform_configs(
    rules: dict[str, Any],
    ext_dir: str,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """加载所有 transform 配置和参考表

    Args:
        rules:   所有语法规则 (dict[str, GrammarRule])
        ext_dir: 增强语法目录路径

    Returns:
        (transform_configs, tables)
        transform_configs: { rule_name: transform_dict }
        tables:           参考表（类型表等）
    """
    configs = load_rules_transform_configs(rules)
    tables = load_type_tables(ext_dir)
    return configs, tables
