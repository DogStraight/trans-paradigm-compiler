"""core/utils.py — 通用工具函数

Doc: docs/component_protocol.md（引擎通用工具）
"""

import os
import json
from typing import Any, Callable
from core.config_registry import declare_cfg
from core.token_protocol import bracket_left, bracket_right

# ── 配置需求（来自 tpc.toml） ──────────────────────────
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
    for _, _, name in token_data.get("pairs", []):
        l = bracket_left(name)
        r = bracket_right(name)
        bracket_map[l] = r
        inverse[r] = l
    return bracket_map, inverse


def square_bracket_types() -> tuple[str, str]:
    """从 lexer.bracket_map 推导方括号开/闭 token 类型（配置驱动，不硬编码）。

    方括号（[ ]）是 @PrimaryExpr 内部下标 / 块头范围的括号区间，linter 的
    lookahead 需据此整体跳过（Level 1 括号配对）。按**字符** "[" 在 [bracket]
    pairs 中定位配对（字符是词法数据，不依赖配对命名——名字叫 square_bracket
    或 bracket 均可）。
    """
    for open_c, _, name in _bracket_cfg.get("pairs", []):
        if open_c == "[":
            return bracket_left(name), bracket_right(name)
    raise RuntimeError(
        "lexer.bracket_map 缺少 '[' 开括号配对，无法推导方括号 token 类型"
    )
