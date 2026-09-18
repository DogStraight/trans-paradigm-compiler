"""style.py — formatter 风格参数加载

从语言包 tpc.toml 的 [formatter.style] 读取（配置驱动，不硬编码）：
  - indent_width: 缩进空格数（默认 4）
  - max_line_width: 折行阈值（默认 100）

缺省值保证无配置也可用（fallback 到代码内默认）。
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
