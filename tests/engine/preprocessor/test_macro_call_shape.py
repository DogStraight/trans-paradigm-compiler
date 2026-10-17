"""`call_shape` 三态声明面（显式"无前缀"）。

- **未声明** `call_shape` ⇒ call 前缀沿用 `shape`（verilog 语义**不变**）；
- `call_shape = "name"` ⇒ **显式无前缀**（前缀 `""`，C 的裸标识符调用）；
- `call_shape = "<token>,name"` ⇒ 显式指定调用前缀；
- 非法形态 / 声明了 `call_shape` 却缺 `call` 段 ⇒ **fail-fast**（不静默降级）。
"""
import pytest

from core.errors import ConfigError
from preprocessor.macro_shape import (
    CALL_SHAPE_KEY,
    KIND_CALL,
    KIND_DIRECTIVE,
    load_macro_shapes,
)

pytestmark = pytest.mark.smoke

_TD = {"symbol": {"base": {"hash": "#", "backtick": "`"}}}


def _shapes(recognition: dict) -> dict:
    return load_macro_shapes(
        cfg={"macro_recognition": recognition}, token_define=_TD
    )


def test_absent_call_shape_keeps_shape_prefix() -> None:
    """未声明 call_shape ⇒ call 前缀沿用 shape（= verilog 现役语义，零变化）。"""
    shapes = _shapes(
        {
            "shape": "symbol.base.backtick,name",
            "directive": ["macro.define"],
            "call": [],
        }
    )
    assert shapes[KIND_DIRECTIVE].prefix == "`"
    assert shapes[KIND_CALL].prefix == "`"


def test_bare_name_call_shape_is_explicit_no_prefix() -> None:
    """`call_shape = "name"` ⇒ 显式无前缀；directive 前缀仍取 `shape`（两者可不同）。"""
    shapes = _shapes(
        {
            "shape": "symbol.base.hash,name",
            "directive": ["macro.define"],
            "call": [],
            CALL_SHAPE_KEY: "name",
        }
    )
    assert shapes[KIND_DIRECTIVE].prefix == "#"
    assert shapes[KIND_CALL].prefix == ""
    assert shapes[KIND_CALL].names == (), "空候选列表 → 名字位任意标识符"


def test_explicit_prefixed_call_shape() -> None:
    """`call_shape = "<token>,name"` ⇒ 显式前缀（同一套两位校验）。"""
    shapes = _shapes(
        {
            "shape": "symbol.base.hash,name",
            "call": [],
            CALL_SHAPE_KEY: "symbol.base.backtick,name",
        }
    )
    assert shapes[KIND_CALL].prefix == "`"


@pytest.mark.parametrize(
    "bad",
    [
        "a,b,c",  # 三位
        "name,name",  # 第二位不是名字位（两位形态要求前缀 token 在前）
        "name,symbol.base.hash",  # 名字位在前 = 后缀序（未实现）
        "symbol.base.hash",  # 单元素但不是名字位占位符
        "",  # 空串
    ],
)
def test_illegal_call_shape_fails_fast(bad: str) -> None:
    with pytest.raises(ConfigError):
        _shapes(
            {
                "shape": "symbol.base.hash,name",
                "call": [],
                CALL_SHAPE_KEY: bad,
            }
        )


def test_call_shape_without_call_section_fails_fast() -> None:
    """声明了 call_shape 但缺 call 形态段 ⇒ fail-fast（配置写错不静默）。"""
    with pytest.raises(ConfigError):
        _shapes(
            {
                "shape": "symbol.base.hash,name",
                "directive": ["macro.define"],
                CALL_SHAPE_KEY: "name",
            }
        )


def test_undeclared_prefix_token_falls_back_when_skip_enabled() -> None:
    """调用方自建 token 表（skip_undeclared_prefix）⇒ 未声明的前缀 token 跳过形态。"""
    shapes = load_macro_shapes(
        cfg={
            "macro_recognition": {
                "shape": "symbol.base.hash,name",
                "call": [],
                CALL_SHAPE_KEY: "symbol.base.nope,name",
            }
        },
        token_define=_TD,
        skip_undeclared_prefix=True,
    )
    assert shapes == {}, "前缀 token 未声明 ⇒ 该形态不启用（不是空前缀）"
