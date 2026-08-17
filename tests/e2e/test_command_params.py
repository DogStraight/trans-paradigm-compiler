"""tests/e2e/test_command_params.py — 指令参数开关（[commands] 声明 + run_pipeline 参数）。

覆盖：语言包 [commands] 以布尔参数开关声明指令、参数组合行为
（format 跳过 analyze/transform 且保留 lint、lint 拦截拼错源码、宏展开还原）。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.e2e.run_pipeline import run_pipeline_on_source
from main import _load_commands


def test_commands_declared_as_params():
    # [commands] 用参数开关声明：format 展开宏 + lint + 渲染，跳过 analyze/transform
    cmds = _load_commands()
    assert set(cmds) >= {"format", "lint", "expand", "pipeline"}
    fmt = cmds["format"]
    assert fmt.get("preprocess") is True  # 宏展开
    assert fmt.get("lint") is True  # 保留 lint（AST 生成需 lint 通过）
    assert fmt.get("analyze") is False  # 跳过 analyze
    assert fmt.get("transform") is False  # 跳过 transform
    assert fmt.get("render") is True
    assert fmt.get("format") is True  # 渲染后过 formatter
    assert cmds["expand"].get("preprocess") is True
    assert cmds["expand"].get("analyze") is True


def test_format_params_reject_lint_error():
    # format 参数组合（跳过 analyze/transform、保留 lint）→ 拼错源码被 lint 拦截
    src = "module m;\n  alwayss @(*) begin\n    a = 1;\n  end\nendmodule\n"
    r = run_pipeline_on_source(
        src,
        quiet=True,
        expand_macros=True,
        no_lint=False,
        analyzer_enabled=False,
        transform_enabled=False,
        renderer_enabled=True,
        format_output=True,
    )
    assert not r["success"]
    assert "lint" in r.get("error", "")


def test_full_pipeline_rejects_lint_error():
    # 完整管线（lint 开启）对拼错源码失败
    src = "module m;\n  alwayss @(*) begin\n    a = 1;\n  end\nendmodule\n"
    r = run_pipeline_on_source(src, quiet=True)
    assert not r["success"]
    assert "lint" in r.get("error", "")


def test_params_expand_macros_restores():
    # expand_macros=True → 宏展开 + 还原（宏定义行保留）
    src = (
        "module m;\n"
        "  `define W 8\n"
        "  reg [`W-1:0] data;\n"
        "  assign out = data;\n"
        "endmodule\n"
    )
    r = run_pipeline_on_source(src, quiet=True, expand_macros=True)
    assert r["success"]
    assert "`define" in r["output"]
