"""tests/e2e/test_command_stages.py — 指令级管线阶段（stages 参数 + [commands] 声明）。

覆盖：语言包 [commands] 声明指令管线、stages 驱动跳过未声明阶段（format 跳过
lint/analyze/transform）、lint 指令只跑 lex+lint、完整阶段成功。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.e2e.run_pipeline import run_pipeline_on_source
from main import _load_commands


def test_commands_declared_in_lang_pack():
    # [commands] 在语言包 tpc.toml 声明：format/lint/expand/pipeline
    cmds = _load_commands()
    assert set(cmds) >= {"format", "lint", "expand", "pipeline"}
    assert "lex" in cmds["format"]["stages"]
    assert "preprocess" in cmds["format"]["stages"]  # format 过宏展开 + 还原
    assert "lint" in cmds["format"]["stages"]  # format 保留 lint（AST 生成需 lint 通过）
    assert "analyze" not in cmds["format"]["stages"]  # format 跳过 analyze/transform
    assert "preprocess" in cmds["expand"]["stages"]


def test_stages_full_pipeline_rejects_lint_error():
    # 拼错源码：完整管线（含 lint）失败
    src = "module m;\n  alwayss @(*) begin\n    a = 1;\n  end\nendmodule\n"
    r = run_pipeline_on_source(src, quiet=True)
    assert not r["success"]
    assert "lint" in r.get("error", "")


def test_stages_format_includes_lint():
    # format 指令 stages 含 lint：拼错源码被 lint 拦截（AST 生成需 lint 通过）
    src = "module m;\n  alwayss @(*) begin\n    a = 1;\n  end\nendmodule\n"
    r = run_pipeline_on_source(
        src, quiet=True, stages=["lex", "lint", "parse", "normalize", "render"]
    )
    assert not r["success"]
    assert "lint" in r.get("error", "")


def test_stages_lint_only():
    # lint 指令：只 lex+lint，报 lint 错误
    src = "module m;\n  alwayss @(*) begin\n    a = 1;\n  end\nendmodule\n"
    r = run_pipeline_on_source(src, quiet=True, stages=["lex", "lint"])
    assert not r["success"]
    assert "lint" in r.get("error", "")


def test_stages_full_success():
    # 完整阶段：正常源码成功并渲染
    src = "module m;\n  assign a = b;\nendmodule\n"
    r = run_pipeline_on_source(
        src,
        quiet=True,
        stages=["lex", "lint", "parse", "normalize", "analyze", "transform", "render"],
    )
    assert r["success"]
    assert "assign" in r["output"]


def test_stages_preprocess_expands_macros():
    # stages 含 preprocess（在 lex 之前）→ 宏展开 + 还原（format 管线语义）
    src = (
        "module m;\n"
        "  `define W 8\n"
        "  reg [`W-1:0] data;\n"
        "  assign out = data;\n"
        "endmodule\n"
    )
    r = run_pipeline_on_source(
        src,
        quiet=True,
        stages=["preprocess", "lex", "lint", "parse", "normalize", "render"],
    )
    assert r["success"]
    assert "`define" in r["output"]  # 宏定义行还原
