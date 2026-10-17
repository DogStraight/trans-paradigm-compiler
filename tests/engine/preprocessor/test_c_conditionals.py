"""C `#if` / `#elif` 整型常量表达式求值（阶段 4 首片 B，声明驱动）。

判据面（均与本机 GCC 16.1.0 `-std=c99 -pedantic-errors -E -P` 对拍）：
- 合法表达式按 C99 §6.10.1 求值（intmax/uintmax 模型、短路、`defined`、宏展开、
  剩余标识符换 0）；
- 非法表达式/常量给结构化诊断（`kind = "condition"`，带 Lx:Cy）；
- 条件块配对错误给诊断（`kind = "condition-balance"`）；
- **inactive 外层 / 已选中分支的 `#elif` 不求值**（C99：被跳过组不求值、不报表达式错）；
- 语言包未声明 `[condition]` ⇒ 不接线（verilog 零变化）；
- 端到端：`run_pipeline_on_source` 下条件块保真（原文还原）且错误是受控 `error`。
"""

import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor import scan_directives, scan_diagnostics
from preprocessor.condition import load_condition_syntax
from pipeline import run_pipeline_on_source

PACK = "grammar/c"


def scan(src: str) -> tuple[list[str], list[dict]]:
    """生产同路扫描 → (活跃行列表, 结构化诊断)。"""
    diags: list[dict] = []
    _t, _f, _b, _p, _d, clean, _m = scan_directives(src, PACK, out_diags=diags)
    lines = [ln for ln in clean.split("\n") if ln and not ln.startswith("//")]
    return lines, diags


def truthy(expr: str, prelude: str = "") -> bool:
    """`#if expr` → 是否取真分支（T / F 两行做判据）。"""
    lines, diags = scan(f"{prelude}#if {expr}\nT\n#else\nF\n#endif\n")
    assert not diags, (expr, diags)
    return lines == ["T"]


# ── 表达式求值（GCC 对拍）────────────────────────────────


@pytest.mark.parametrize(
    "expr",
    [
        "1",
        "1 + 2 * 3 == 7",
        "(1)",
        "1 ? 2 : 3",
        "-1 < 0" ,
        "~0 == -1",
        "!1 == 0",
        "1 == 1 == 1",
        "1 <= 2 != 0",
        "1 && 2 & 3",
        "9223372036854775807 == 0x7FFFFFFFFFFFFFFF",
        "1u - 2 > 0",
        "0u - 1 == 0xFFFFFFFFFFFFFFFF",
        "-1 < 0xFFFFFFFF",  # 十六进制常量装得进 intmax ⇒ 有符号（gcc 实测）
        "0xFFFFFFFF + 0 > -1",
        "0xFFFFFFFFFFFFFFFF == -1",
        "18446744073709551615u > 0",
        "0x1000000000000000 > 0",
        "'a' == 97",
        "'\\n' == 10",
        "'\\x41' == 65",
        "'\\377' == -1",  # plain char 有符号扩展（gcc 实测）
        "'\\200' == -128",
        "'ab' == 0x6162",
        "'\\377\\377' == 65535",
        "L'a' == 97",
        "L'ab' == 98",  # 带前缀多字符取最后字符（gcc 实测）
        "-3 / 2 == -1",
        "-3 % 2 == -1",
        "3 % -2 == 1",
        "-1 >> 1 == -1",
        "0xFFFFFFFFFFFFFFFF >> 1 == 0x7FFFFFFFFFFFFFFF",
        "1 << 62 == 4611686018427387904",
        "1 << -1 == 0",  # gcc 负计数反向移位（UB 面按 oracle 口径）
        "-4 >> -1 == -8",
        "-1 >> 64 == -1",
        "(1u << 64) == 0",
        "0 ? 0 : 1 ? 2 : 3",
        "1 == 1 != 0",
    ],
)
def test_condition_true_forms(expr):
    """合法表达式按 gcc 口径取真。"""
    assert truthy(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "0",
        "1 > 2",
        "-1 < 0u",
        "1u > -1",
        "0xFFFFFFFFu > -1",
        "-1 >> -1 == -1",
        "0 && 1",
        "1 && 0",
        "1 << -1",
    ],
)
def test_condition_false_forms(expr):
    """合法表达式按 gcc 口径取假。"""
    assert not truthy(expr)


def test_defined_both_forms_and_macro_operand_not_expanded():
    """`defined X` / `defined(X)`；操作数**不**宏展开（`A` 定义即真，即使 A 展开成宏名）。"""
    src = (
        "#define A B\n"
        "#if defined(A) && !defined B\n"
        "OK\n"
        "#else\n"
        "BAD\n"
        "#endif\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["OK"]


def test_undefined_identifier_becomes_zero():
    """剩余标识符换 0（C99 §6.10.1p4；未定义名不报错）。"""
    lines, diags = scan("#if UNDEFINED_X == 0\nZ\n#else\nNZ\n#endif\n")
    assert not diags
    assert lines == ["Z"]


def test_macro_expansion_is_raw_tokens():
    """宏替换是**裸 token** 代入（不加括号）：`EXPR*2` = `1+2*2`（gcc 实测取假）。"""
    src = "#define EXPR 1+2\n#if EXPR*2 == 6\nEQ\n#else\nNE\n#endif\n"
    lines, diags = scan(src)
    assert not diags
    assert lines == ["NE"]


def test_function_macro_in_condition():
    """函数宏在条件表达式里参与宏展开。"""
    src = "#define ADD(a,b) ((a)+(b))\n#if ADD(1,2) == 3\nFM\n#endif\n"
    lines, diags = scan(src)
    assert not diags
    assert lines == ["FM"]


def test_macro_defined_after_first_condition_is_visible():
    """宏表**活值**语义：后文 `#define` 对后文 `#if` 生效（求值环境不缓存宏表快照）。"""
    src = (
        "#if A\nWRONG\n#else\nFIRST\n#endif\n"
        "#define A 1\n"
        "#if A\nSECOND\n#endif\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["FIRST", "SECOND"]


def test_condition_comments_and_continuation():
    """条件表达式里的注释 = 空白；反斜杠续行在扫描前合并。"""
    src = (
        "#if 1 /* c */ + 2 == 3\nOK1\n#endif\n"
        "#if 1 // c\nOK2\n#endif\n"
        "#if 1 + \\\n2 == 3\nOK3\n#endif\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["OK1", "OK2", "OK3"]


# ── 诊断面（表达式错误）────────────────────────────────


@pytest.mark.parametrize(
    "expr,needle",
    [
        ("1/0", "除数为零"),
        ("1%0", "除数为零"),
        ("9223372036854775807 + 1", "整数溢出"),
        ("1 << 64", "整数溢出"),
        ("18446744073709551615", "整数常量"),
        ("0x10000000000000000", "整数常量"),
        ("1lL", "记号"),
        ("(1", "缺 ')'"),
        ("1)", "多余"),
        ("1 +", "不完整"),
        ("1 2", "多余"),
        ("1.0", "记号"),
        ('"x"', "字符串"),
        ("= 1", "记号"),
        ("sizeof(int)", "多余"),
        ("1 ? 2", "三目"),
        ("defined()", "defined"),
        ("'\\x100'", "转义"),
        ("L'\\xffffffff'", "转义"),
    ],
)
def test_condition_error_reports(expr, needle):
    """非法表达式/常量 → `condition` 诊断（带 line/column），且不抛异常。"""
    lines, diags = scan(f"#if {expr}\nX\n#endif\n")
    assert lines == []
    cond = [d for d in diags if d["kind"] == "condition"]
    assert cond, (expr, diags)
    assert needle in cond[0]["message"], (expr, cond[0]["message"])
    assert cond[0]["line"] == 1
    assert isinstance(cond[0]["column"], int) and cond[0]["column"] >= 1


def test_empty_expression_reports():
    """`#if` 后只有注释 ⇒ 表达式为空（gcc: #if with no expression）。"""
    lines, diags = scan("#if /* nothing */\nX\n#endif\n")
    assert lines == []
    assert [d["kind"] for d in diags] == ["condition"]
    assert "空" in diags[0]["message"]


# ── 短路与跳过组（不求值）──────────────────────────────


def test_short_circuit_suppresses_arithmetic_errors():
    """短路只抑制**算术诊断**（除零/溢出），值语义仍按短路。"""
    for expr in ("0 && 1/0", "1 || 1/0", "1 ? 2 : 1/0", "0 ? 1/0 : 2"):
        _lines, diags = scan(f"#if {expr}\nT\n#else\nF\n#endif\n")
        assert not diags, (expr, diags)
    assert truthy("1 || 1/0")
    assert not truthy("0 && 1/0")
    assert truthy("1 ? 2 : 1/0")


def test_short_circuit_does_not_hide_parse_errors():
    """短路不抑制**语法/字面量类**诊断（gcc 实测：`0 && 1.0` 报错）。"""
    _lines, diags = scan("#if 0 && 1.0\nX\n#endif\n")
    assert [d["kind"] for d in diags] == ["condition"]


def test_skipped_group_not_evaluated():
    """inactive 外层里的 `#if` 表达式不求值、不报错（含语法错/除零）。"""
    src = "#if 0\n#if (1\nX\n#endif\n#endif\nOK\n"
    lines, diags = scan(src)
    assert not diags
    assert lines == ["OK"]


def test_elif_after_taken_branch_not_evaluated():
    """已选中分支后的 `#elif` 不求值（gcc 实测：`#elif 1/0` 不报错）。"""
    src = "#if 1\nA\n#elif 1/0\nB\n#elif (bad\nC\n#endif\nOK\n"
    lines, diags = scan(src)
    assert not diags
    assert lines == ["A", "OK"]


def test_elif_evaluated_when_previous_false():
    """前面分支全假时 `#elif` 求值（错误照报）。"""
    _lines, diags = scan("#if 0\nA\n#elif 1/0\nB\n#endif\n")
    assert [d["kind"] for d in diags] == ["condition"]


def test_elif_chain_first_true_wins():
    """`#if`→`#elif` 链：首个为真分支生效，其余不求值。"""
    src = "#if 0\nA\n#elif 1\nB\n#elif 1\nC\n#else\nD\n#endif\n"
    lines, diags = scan(src)
    assert not diags
    assert lines == ["B"]


def test_skipped_group_define_not_applied():
    """`#if 0` 里的 `#define` 不生效（C99；含 `defined` 判定）。"""
    src = (
        "#if 0\n#define X 1\n#endif\n"
        "#if defined(X)\nD\n#else\nU\n#endif\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["U"]


def test_ifdef_family_still_macro_name_semantics():
    """C 的 `#ifdef` / `#ifndef` 仍是**宏名**语义；`#elif` 可接在 `#ifdef` 后。"""
    src = (
        "#define A\n"
        "#ifdef A\nIFDEF\n#endif\n"
        "#ifndef B\nIFNDEF\n#endif\n"
        "#ifdef B\nX\n#elif 1\nELIF_AFTER_IFDEF\n#endif\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["IFDEF", "IFNDEF", "ELIF_AFTER_IFDEF"]


# ── 条件块配对诊断 ─────────────────────────────────────


@pytest.mark.parametrize(
    "src,needle",
    [
        ("#if 1\nX\n", "未闭合"),
        ("#endif\nX\n", "多余"),
        ("#else\nX\n", "多余"),
        ("#elif 1\nX\n", "多余"),
        ("#if 0\nA\n#else\nB\n#else\nC\n#endif\n", "重复"),
        ("#if 0\nA\n#else\nB\n#elif 1\nC\n#endif\n", "之后"),
        ("#ifdef X\nA\n", "未闭合"),
        ("#ifdef\nA\n#endif\n", "缺宏名"),
    ],
)
def test_condition_balance_reports(src, needle):
    """条件块配对错误 → `condition-balance` 诊断（C 标准要求诊断）。"""
    _lines, diags = scan(src)
    balance = [d for d in diags if d["kind"] == "condition-balance"]
    assert balance, (src, diags)
    assert needle in balance[0]["message"], (src, balance[0]["message"])


def test_nested_conditions_ok():
    """嵌套条件块（含 `#if`/`#ifdef` 混合）无配对误报。"""
    src = (
        "#define A 1\n"
        "#if A\n"
        "#ifdef A\n"
        "#if 0\nB\n#elif 1\nC\n#endif\n"
        "#endif\n"
        "#endif\n"
        "D\n"
    )
    lines, diags = scan(src)
    assert not diags
    assert lines == ["C", "D"]


# ── 声明面 / 未接线语言 ────────────────────────────────


def test_condition_declaration_is_source():
    """C 声明了 `[condition]`；verilog 未声明 ⇒ 不求值（语义不变）。"""
    syn = load_condition_syntax(PACK)
    assert syn is not None
    assert syn.defined == "defined"
    assert syn.intmax_bits == 64
    assert len(syn.infix) == 19
    assert [op.action for op in syn.prefix] == [
        "unary-plus",
        "unary-minus",
        "logical-not",
        "bitwise-not",
    ]
    assert load_condition_syntax(DEFAULT_RULES_DIR) is None


def test_verilog_not_wired():
    """verilog 未声明 `[condition]`：`#if` 不是指令、不被求值（A/B 零变化口径）。"""
    assert scan_diagnostics("#if 1/0\nX\n", DEFAULT_RULES_DIR) == []


# ── 端到端（管线 / CLI 共用入口）──────────────────────


def test_pipeline_condition_blocks_preserved():
    """管线：条件块原文保真（活跃分支进 AST、非活跃走占位还原）+ 复跑幂等。"""
    src = (
        "#define N 4\n"
        "#if N > 3\n"
        "int big = 1;\n"
        "#else\n"
        "int small = 0;\n"
        "#endif\n"
    )
    res = run_pipeline_on_source(source=src, quiet=True, rules_dir=PACK)
    assert res["success"], res.get("error")
    assert "#if N > 3" in res["output"]
    assert "int big = 1;" in res["output"]
    assert "int small = 0;" in res["output"]
    r2 = run_pipeline_on_source(
        source=res["output"], quiet=True, rules_dir=PACK
    )
    assert r2["success"], r2.get("error")
    assert r2["output"] == res["output"]


def test_pipeline_condition_error_is_controlled():
    """条件表达式错误 ⇒ 受控 `error`（非异常）+ `preprocessor_errors` 结构化。"""
    res = run_pipeline_on_source(
        source="#if 1/0\nint x;\n#endif\n", quiet=True, rules_dir=PACK
    )
    assert res["success"] is False
    assert "除数为零" in res["error"]
    kinds = [d["kind"] for d in res.get("preprocessor_errors") or []]
    assert kinds == ["condition"]


def test_scan_diagnostics_surfaces_condition_errors():
    """CLI 两路径共用入口 `scan_diagnostics` 覆盖条件诊断（带位置）。"""
    diags = scan_diagnostics("#if 1/0\nX\n#endif\n", PACK)
    assert [d["kind"] for d in diags] == ["condition"]
    assert diags[0]["line"] == 1 and diags[0]["column"] == 6
