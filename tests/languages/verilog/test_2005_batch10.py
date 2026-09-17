"""tests/languages/verilog/test_2005_batch10.py — 端口默认值宏（M1，ice40 默认配置）。

2026-08-28 目标 1 收尾批次：ice40 cells_sim **默认配置**（不预定义
NO_ICE40_DEFAULT_ASSIGNMENTS）可解析。此前 `input NAME `M`（M body=
`= 1'b1`，端口默认值位）替换成标识符占位 → `input NAME tpc_marker_N`
两个相邻标识符，linter/parser 双拒（34 错），只能靠 NO_ICE40 空宏（注释锚）规避。

修复（现机制）：赋值后缀宏与其他非空体宏同路——**宏体文本铺进流**，parser
看到的就是 `input NAME = 1'b1`（Declarator @Init? 兜住端口默认值），
还原走宏区间 raw 拼接（宏体不再占语法位）。

连带验证：带参形态 `ICE40_DEFAULT_ASSIGNMENT_V(v)`（body=`= v`）与
对象宏 `ICE40_DEFAULT_ASSIGNMENT_0/1` 同路径；ice40 全文件默认配置
在 test_real_corpus.py 门禁（manifest 预定义改为空）。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def _flat(text: str) -> str:
    return "".join(text.split())


# ── 端口默认值宏（赋值后缀形态，M1 核心） ────────────────────────────


def test_port_default_object_macro():
    """`input CLOCK_ENABLE `M`（body=`= 1'b1`）默认配置可解析 + 还原保真。"""
    src = (
        "`define ICE40_DEFAULT_ASSIGNMENT_1 = 1'b1\n"
        "module m (\n"
        "\tinput  CLOCK_ENABLE `ICE40_DEFAULT_ASSIGNMENT_1,\n"
        "\tinput  A,\n"
        "\toutput B\n"
        ");\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    out = r.get("output", "")
    assert "`ICE40_DEFAULT_ASSIGNMENT_1" in out  # 宏调用还原（保真）
    assert "tpc:" not in out  # 无占位残留
    # 端口名不被顶掉：CLOCK_ENABLE 必须出现，且不再有孤立 marker token
    assert "CLOCK_ENABLE" in out


def test_port_default_func_macro():
    """带参形态 `ICE40_DEFAULT_ASSIGNMENT_V(v)`（body=`= v`）同路径。"""
    src = (
        "`define ICE40_DEFAULT_ASSIGNMENT_V(v) = v\n"
        "module m (\n"
        "\tinput  CLOCK_ENABLE `ICE40_DEFAULT_ASSIGNMENT_V(1'b0),\n"
        "\toutput B\n"
        ");\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    out = r.get("output", "")
    assert "`ICE40_DEFAULT_ASSIGNMENT_V(1'b0)" in out
    assert "tpc:" not in out


def test_port_default_inout_and_output():
    """inout/output 端口默认值宏同样还原（非 input 专属路径）。"""
    src = (
        "`define D0 = 1'b0\n"
        "module m (\n"
        "\tinout PAD `D0,\n"
        "\toutput O `D0\n"
        ");\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    out = r.get("output", "")
    assert out.count("`D0") == 2  # 两处宏调用都还原
    assert "tpc:" not in out


def test_port_default_lint_clean():
    """默认配置 lint 零诊断（此前 34 错的根因场景）。"""
    src = (
        "`define ICE40_DEFAULT_ASSIGNMENT_1 = 1'b1\n"
        "module m (\n"
        "\tinput  CLOCK_ENABLE `ICE40_DEFAULT_ASSIGNMENT_1,\n"
        "\toutput B\n"
        ");\n"
        "endmodule\n"
    )
    r = run_pipeline_on_source(
        source=src, quiet=True, expand_macros=True, no_lint=False
    )
    assert r["success"]
    assert r.get("error", "") == ""


def test_port_default_idempotent():
    """默认配置输出再走一遍管线稳定（幂等）。"""
    src = (
        "`define ICE40_DEFAULT_ASSIGNMENT_1 = 1'b1\n"
        "module m (\n"
        "\tinput  CLOCK_ENABLE `ICE40_DEFAULT_ASSIGNMENT_1,\n"
        "\toutput B\n"
        ");\n"
        "endmodule\n"
    )
    r1 = _run(src, expand_macros=True)
    assert r1["success"]
    out1 = r1.get("output", "")
    r2 = _run(out1, expand_macros=True)
    assert r2["success"]
    assert _flat(r2.get("output", "")) == _flat(out1)


# ── 非端口位赋值后缀宏（同路径但不破坏既有行为） ─────────────────────


def test_assign_init_macro_keeps_token_path():
    """声明初始化位 `reg a = `M`（body=`= 1'b1`）也走 inline+body 还原。"""
    src = (
        "`define D1 = 1'b1\n"
        "module m;\n"
        "\treg a `D1;\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    out = r.get("output", "")
    assert "`D1" in out
    assert "tpc:" not in out


def test_non_assignment_macro_unchanged():
    """普通对象宏（body 不以 `=` 开头）同路，行为不变。"""
    src = (
        "`define TV80DELAY 1\n"
        "module m;\n"
        "\twire [`TV80DELAY-1:0] x;\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    out = r.get("output", "")
    assert "`TV80DELAY" in out
    assert "tpc:" not in out


def test_body_strip_prefix_detection():
    """body 前导空白不影响 `=` 判定（`.lstrip().startswith('=')`）。"""
    src = (
        "`define D = 1'b1\n"
        "module m (\n"
        "\tinput A `D,\n"
        "\toutput B\n"
        ");\n"
        "endmodule\n"
    )
    r = _run(src, expand_macros=True)
    assert r["success"]
    assert "`D" in r.get("output", "")
