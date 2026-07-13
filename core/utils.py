"""core/utils.py — 通用工具函数"""

import os
import json
from typing import Any, Optional, Callable


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建。"""
    os.makedirs(path, exist_ok=True)


def save_json(
    data: Any, path: str, label: str = "", log_fn: Optional[Callable] = None
) -> None:
    """将 data 写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if label:
        (log_fn or print)(f"[{label}] saved ({os.path.getsize(path)} bytes)")


def get_bracket_map() -> tuple[dict[str, str], dict[str, str]]:
    """从 ConfigRegistry 加载括号映射，返回 (正向映射, 反向映射)。

    配置源：lexer.token_base → [bracket] pairs = [[open, close, name], ...]
    正向映射：bracket.l_{name} → bracket.r_{name}
    反向映射：bracket.r_{name} → bracket.l_{name}
    """
    from core.config_registry import config as _cfg

    token_data = _cfg.get("lexer.token_base")
    bracket_map: dict[str, str] = {}
    inverse: dict[str, str] = {}
    for _, _, name in token_data.get("bracket", {}).get("pairs", []):
        l = f"bracket.l_{name}"
        r = f"bracket.r_{name}"
        bracket_map[l] = r
        inverse[r] = l
    return bracket_map, inverse
