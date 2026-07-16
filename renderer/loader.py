"""
loader.py — TOML 布局规则 / 风格加载

从 TOML 规则目录加载 layout 定义和风格参数。
风格参数通过 ConfigRegistry 声明式加载。
"""

import tomllib
import os
from core.config_registry import config
from core.config_map import RENDERER_STYLE


def load_layouts(rules_dir: str, layouts: dict) -> None:
    """从 TOML 规则目录加载所有 layout 定义到 layouts 字典（递归子目录）"""
    from core.define import FileManager

    base = FileManager.get_full_path(rules_dir)
    if not os.path.isdir(base):
        return

    for fname in sorted(os.listdir(base)):
        if fname.startswith("_"):
            continue
        fpath = os.path.join(base, fname)
        # 子目录递归
        if os.path.isdir(fpath) and "." not in fname:
            sub = os.path.join(rules_dir, fname).replace("\\", "/")
            load_layouts(sub, layouts)
            continue
        if not fname.endswith(".toml"):
            continue
        with open(fpath, "rb") as f:
            data = tomllib.load(f)
        for node_type, cfg in data.items():
            if not isinstance(cfg, dict):
                continue
            layout = cfg.get("renderer")
            if layout and any(k in layout for k in ("layout", "head", "body", "tail")):
                if node_type in layouts:
                    layouts[node_type].update(layout)
                else:
                    layouts[node_type] = layout


def load_style(rules_dir: str) -> dict:
    """加载风格配置：从 ConfigRegistry 获取 base 和 lang 风格。

    返回 {'indent_str': str, 'max_inline': int, 'children_field': str}
    """
    result = {
        "indent_str": "    ",
        "max_inline": 40,
        "children_field": "sub_node",
    }

    # base/_style.toml（required=False，没有就用默认值）
    for key in (RENDERER_STYLE,):
        try:
            style = config.get(key)
            if not isinstance(style, dict):
                continue
            if "indent" in style:
                val = style["indent"]
                if isinstance(val, int):
                    result["indent_str"] = " " * val
                else:
                    result["indent_str"] = val
            if "max_inline" in style:
                result["max_inline"] = style["max_inline"]
            if "children_field" in style:
                result["children_field"] = style["children_field"]
        except KeyError:
            continue

    return result
