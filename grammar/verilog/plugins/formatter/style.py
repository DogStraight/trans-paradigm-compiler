"""style.py — formatter 风格参数加载 + 行首缩进量化

从语言包 tpc.toml 的 [formatter.style] 读取（配置驱动，不硬编码）：
  - indent_width: 缩进空格数（默认 4）
  - max_line_width: 折行阈值（默认 100）

缺省值保证无配置也可用（fallback 到代码内默认）。`line_indent_width` 是各
pass 共用的行首空白量化（原先在 `passes/indent.py` / `passes/ifdef.py` 各存
一份同体实现）。
"""

from __future__ import annotations


def load_style() -> dict:
    """加载 formatter 风格参数。"""
    result = {
        "indent_width": 4,
        "max_line_width": 100,
    }
    try:
        from core.config_registry import ConfigRegistry
        cfg = ConfigRegistry.get("formatter.style")
    except (KeyError, RuntimeError):
        # 未声明 / 未加载 → 用上面代码内默认（只认这两种，其它异常照抛）
        return result
    if isinstance(cfg, dict):
        if "indent_width" in cfg:
            result["indent_width"] = int(cfg["indent_width"])
        if "max_line_width" in cfg:
            result["max_line_width"] = int(cfg["max_line_width"])
    return result


def line_indent_width(line: str) -> int:
    """行首空白宽度（tab 折 4 空格；遇首个非空白字符即停）。

    formatter 各 pass 共用一份量化：需要级数时用
    `line_indent_width(line) // indent_width`。
    """
    n = 0
    for c in line:
        if c == "\t":
            n += 4
        elif c == " ":
            n += 1
        else:
            break
    return n
