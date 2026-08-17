"""tests/e2e/test_command_params.py — 指令参数开关（[commands] 声明 + run_pipeline 参数）。

覆盖：语言包 [commands] 以布尔参数开关声明指令、参数组合行为
（format 跳过 analyze/transform 且保留 lint、lint 拦截拼错源码、宏展开还原）。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.e2e.run_pipeline import run_pipeline_on_source
from main import _load_commands, _resolve_command


def test_commands_declared_as_params():
    # [commands] 只声明差异项（默认 = 完整管线全 true）；_resolve_command 合并默认。
    cmds = _load_commands()
    assert set(cmds) >= {"format", "lint", "expand", "pipeline"}
    # 语言包只声明差异项——expand/pipeline 无任何显式参数（纯默认 + formatter）
    fmt = _resolve_command("format")
    assert fmt.get("preprocess") is True  # 默认：宏展开
    assert fmt.get("lint") is True  # 默认：保留 lint（AST 生成需 lint 通过）
    assert fmt.get("analyze") is False  # 差异项：跳过 analyze
    assert fmt.get("transform") is False  # 差异项：跳过 transform
    assert fmt.get("render") is True
    assert fmt.get("plugins", {}).get("formatter") is True  # 插件能力：formatter
    exp = _resolve_command("expand")
    assert exp.get("preprocess") is True
    assert exp.get("analyze") is True
    assert exp.get("plugins", {}).get("formatter") is True
    lint_cmd = _resolve_command("lint")
    assert lint_cmd.get("parse") is False  # 差异项：lint 只 lint 不 parse
    assert lint_cmd.get("analyze") is False
    assert lint_cmd.get("render") is False
    # 未声明的指令名 → 纯默认（完整管线）
    unknown = _resolve_command("nonexistent")
    assert unknown.get("preprocess") is True
    assert unknown.get("parse") is True
    assert unknown.get("plugins", {}).get("formatter") is False


def test_lint_only_does_not_parse():
    # parse_enabled=False：lint 通过即成功，不 parse（无 ast）
    src = "module m;\n  assign a = b;\nendmodule\n"
    r = run_pipeline_on_source(src, quiet=True, parse_enabled=False)
    assert r["success"]
    assert r["ast"] is None


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
