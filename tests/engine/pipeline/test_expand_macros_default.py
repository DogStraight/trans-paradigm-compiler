"""默认口径：`expand_macros` 库默认与 CLI 默认一致（A2 ①，gap ⑬）。

事故（2026-10-17 实测）：CLI 默认 **True**（`main.py` 按 `[commands].preprocess`）而库默认 **False**
（`pipeline/__init__.py` 兜底 + `config/tpc_config.json`）⇒ 同一输入两条路径 verdict 不同：
合法 `#define FOO 1` 在库默认下报 `parse truncated`，CLI 下正常。

本文件钉住三处，任一侧被改回 False 都会变红：
1. 库默认路径（不传参）真的展开；2. 项目配置默认值；3. 配置缺键时的兜底（wheel 安装无项目配置）。
"""

import json
from pathlib import Path

import pytest

from pipeline import _resolve_defaults, run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_library_default_expands_c_macro() -> None:
    """库默认（不传 `expand_macros`）走预处理：合法 `#define` 不再 `parse truncated`。"""
    r = run_pipeline_on_source(
        "#define FOO 1\nint x = FOO;\n", rules_dir="grammar/c", quiet=True
    )
    assert r["success"], r["error"]
    assert r["error"] == ""
    assert "1" in r["output"]


def test_config_default_is_expand_macros_true() -> None:
    """项目配置默认值 = **开**（与 CLI 的 `[commands].preprocess` 默认一致）。"""
    raw = (_ROOT / "config" / "tpc_config.json").read_text(encoding="utf-8")
    assert json.loads(raw)["pipeline"]["expand_macros"] is True


def test_unconfigured_fallback_is_expand_macros_true() -> None:
    """配置缺键时兜底（wheel 安装无项目配置）= **开**。"""
    resolved = _resolve_defaults({}, {"expand_macros": None})
    assert resolved["expand_macros"] is True
