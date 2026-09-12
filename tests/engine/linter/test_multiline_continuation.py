"""行首运算符续行（多行语句）——linter 与 parser 共用的 pratt 判据。

根因（2026-09-13 trace 实证）：pratt 中缀循环"遇 newline 非运算符自然
break"，把 `ALL0\\n + ALL1` 截在 `ALL0` → 语句匹配器随后要求 `;` 却遇到
`+` → 整句判不出（`phase-unrecognized` 误报，无宏也触发）。

判据：跳过 trivia 后若下一个显著 token 是**中缀**运算符 → 表达式续行
（行首中缀运算符不可能是语句起点）；否则维持"语句级换行终止"不变量
（`expr1\\n expr2` 不粘连成一句）。

Doc: parser/pratt_parser.py（中缀循环续行判据）
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src: str, **kw) -> dict:
    return run_pipeline_on_source(source=src, quiet=True, **kw)


_MULTI = (
    "module m;\n"
    "  reg clk;\n"
    "  reg [31:0] XSIMM, ALL0, ALL1, IDATAX;\n"
    "  always @(posedge clk) begin\n"
    "    XSIMM <= ALL0\n"
    "        + ALL1\n"
    "        + IDATAX;\n"
    "  end\n"
    "endmodule\n"
)


def test_multiline_leading_operator_lints_clean() -> None:
    """行首运算符续行：lint 不再误报（原 3 条 phase-unrecognized）。"""
    res = _run(_MULTI)
    assert res["success"], res.get("error")


def test_multiline_leading_operator_parses() -> None:
    """同一形态解析成功（parser 与 linter 共用同一判据）。"""
    res = _run(_MULTI, no_lint=True)
    assert res["success"], res.get("error")
    assert "XSIMM" in res["output"]


def test_two_multiline_statements_stay_separate() -> None:
    """不变量：连续两个多行语句各自成句，不被续行判据粘连。"""
    src = (
        "module m;\n"
        "  reg clk;\n"
        "  reg [31:0] a, b, c, d;\n"
        "  always @(posedge clk) begin\n"
        "    a = b\n"
        "        + c;\n"
        "    d = a\n"
        "        + b;\n"
        "  end\n"
        "endmodule\n"
    )
    res = _run(src)
    assert res["success"], res.get("error")


def test_statement_after_expression_not_glued() -> None:
    """不变量：表达式后换行的**下一个非运算符 token** 仍是新语句（不续行）。"""
    src = (
        "module m;\n"
        "  reg clk;\n"
        "  reg [31:0] a, b, c, d;\n"
        "  always @(posedge clk) begin\n"
        "    a = b + c\n"
        "    d = a;\n"
        "  end\n"
        "endmodule\n"
    )
    res = _run(src)
    # 缺 `;` 的语句必须仍被判出（续行判据只认中缀运算符，不认 id——
    # 若被误粘连成一句，`d = a;` 会被当成续行内容，此处会静默通过）。
    assert not res["success"], res.get("error")
