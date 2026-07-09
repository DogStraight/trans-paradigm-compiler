"""core/utils.py — 通用工具函数"""

import os
import json
from typing import Any, Optional


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建。"""
    os.makedirs(path, exist_ok=True)


def save_json(data: Any, path: str, label: str = "", log_fn: Optional[callable] = None) -> None:
    """将 data 写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if label:
        (log_fn or print)(f"[{label}] saved ({os.path.getsize(path)} bytes)")
