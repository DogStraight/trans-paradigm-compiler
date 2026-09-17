"""linter 与管线宏处理同源（0.1.2 阶段 3）：单一来源门禁。

阶段 3 目标 = "形态判定同一份配置，避免双实现漂移"。侦察结论：已成立——
linter（`linter/scanner.py`）与管线（`pipeline/__init__.py`）都调用
`preprocessor._expand.expand_tokens`（同一函数对象），形态配置由
`preprocessor/macro_shape.py` 单一读取语言包 `[macro_shape]`。本文件用断言
**锁定**这两点，防未来任一路径私自复制一份实现/配置。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor.macro_shape import get_suffix_leads

pytestmark = pytest.mark.smoke

_SRC = (
    "module m;\n"
    "`define BODY x = 1'b1;\n"
    "  reg x;\n"
    "  initial begin\n"
    "    `BODY\n"
    "  end\n"
    "endmodule\n"
)


def test_both_paths_share_same_expander() -> None:
    """linter 与管线调用**同一** expand_tokens（无第二实现）。"""
    from linter import scanner as linter_scanner
    from pipeline import expand_tokens as pipeline_expand
    from preprocessor._expand import expand_tokens as canonical

    assert linter_scanner.expand_tokens is canonical
    assert pipeline_expand is canonical


def test_shape_config_single_source() -> None:
    """形态声明单一来源 = 语言包 TOML（引擎不硬编码副本）。"""
    from core.config_registry import ConfigRegistry

    leads = get_suffix_leads()
    assert leads, "语言包未提供 suffix_leads"

    raw = ConfigRegistry._loaded.get("preprocessor.macro_shape") or {}
    assert list(raw.get("suffix_leads") or []) == list(leads)


def test_linter_accepts_defined_macro_source() -> None:
    """linter 与管线对含宏源码的处理一致：已定义宏不报 undefined-macro，且
    管线 format 成功（两条路径的宏展开行为一致）。"""
    from linter.scanner import LinterScanner
    from pipeline import run_pipeline_on_source

    scanner = LinterScanner(rules_dir=DEFAULT_RULES_DIR)
    codes = {d.code for d in scanner.scan(_SRC)}
    assert "undefined-macro" not in codes

    res = run_pipeline_on_source(
        source=_SRC, quiet=True, no_lint=True, expand_macros=True
    )
    assert res["success"], res.get("error")
    assert "tpc_marker" not in res["output"]
    assert "`BODY" in res["output"]


def test_linter_flags_undefined_macro() -> None:
    """回归锁定：未定义宏仍报（形态判定不放松既有检查）。"""
    from linter.scanner import LinterScanner

    src = "module m;\n  assign a = `NOT_DEFINED;\nendmodule\n"
    scanner = LinterScanner(rules_dir=DEFAULT_RULES_DIR)
    codes = {d.code for d in scanner.scan(src)}
    assert "undefined-macro" in codes
