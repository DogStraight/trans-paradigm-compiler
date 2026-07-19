"""core/utils.py — 通用工具函数"""

import os
import json
from typing import Any, Callable
from core.config_registry import declare_cfg

# ── 配置需求（来自 pyv.toml） ──────────────────────────
# lexer.bracket_map
#   #sym:config = [bracket]
#   格式: dict — { pairs: [[open, close, name], ...] }
_bracket_cfg: dict = declare_cfg("lexer.bracket_map", {}, __name__, "_bracket_cfg")


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建。"""
    os.makedirs(path, exist_ok=True)


def save_json(
    data: Any, path: str, label: str = "", log_fn: Callable | None = None
) -> None:
    """将 data 写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if label:
        (log_fn or print)(f"[{label}] saved ({os.path.getsize(path)} bytes)")


def get_bracket_map() -> tuple[dict[str, str], dict[str, str]]:
    """从 ConfigRegistry 加载括号映射，返回 (正向映射, 反向映射)。

    配置源：lexer.bracket_map → [bracket] pairs = [[open, close, name], ...]
    正向映射：bracket.l_{name} → bracket.r_{name}
    反向映射：bracket.r_{name} → bracket.l_{name}
    """
    token_data = _bracket_cfg
    bracket_map: dict[str, str] = {}
    inverse: dict[str, str] = {}
    for _, _, name in token_data.get("bracket", {}).get("pairs", []):
        l = f"bracket.l_{name}"
        r = f"bracket.r_{name}"
        bracket_map[l] = r
        inverse[r] = l
    return bracket_map, inverse
