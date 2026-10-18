"""跨行宏调用（token 级边界的另一半：**实参跨行** / **名字-括号跨行**）。

背景（A1 已声明边界②，循环 #24 落地）：文本层逐行展开 ⇒ `F(1,` 与下一行 `2)` 收不
到一起；`F` 与换行后的 `(2)` 同。C 预处理 token 序列**不区分换行**（换行只是预处理
空白）⇒ 调用可跨行。本轮在保持**行数不变**的前提下支持：
首行 = 行首~调用列 + 宏体；中间被吞行置空；尾行 = 闭括号后原文。行映射仍按
"clean 源行 → 输出行"对齐（诊断回源/渲染回插既有机制不变）。

**判据口径**：token 序列对 GCC 16.1.0 `-E -P`（空白/换行/注释不计——GCC 输出会
删注释，tpc 展开文本保留注释 trivia 但 token 等价）。判据分三级：
- `CRITERIA`（**改前红**）：跨行展开出的 token 序列；
- `GUARDS`（改前绿，守卫"没把非调用拼成调用"）：未配平、名字后第一个 token 非
  开括号、非 splice 处置（verilog 空体宏 line/inline）保持不展开；
- `MAPPING`：`out_to_src` 行数/取值、区域 source_text/切片、渲染 raw 回插保真。
"""
import re

import pytest

from preprocessor import scan_directives
from preprocessor._expand import expand_tokens
from preprocessor.macro_expand import mask_spans, tokenize
from preprocessor.macro_shape import load_macro_operators
from lexer.comment_syntax import load_comment_syntax

pytestmark = pytest.mark.smoke

PACK = "grammar/c"
_VPACK = "grammar/verilog"
_OPS = load_macro_operators(rules_dir=PACK)
_SYNTAX = load_comment_syntax(PACK)
_MARKS = re.compile(r"\s*//\s*<tpc:directive:\d+>\s*")


def _expand(src: str, pack: str = PACK):
    """生产同路：扫指令 → 展开；返回 (输出, 区域, 行映射)。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, pack)
    out, _stack, regions, line_map = expand_tokens(
        clean, macro_defs, rules_dir=pack, func_macros=func_macros
    )
    return out, regions, line_map, clean


def _tokens(text: str) -> list[str]:
    """token 文本序列：空白与注释不算（换行/缩进/注释 trivia 在两侧不同）。"""
    ops = _OPS
    spans = mask_spans(text, ops.string_delimiters, ops.escape, _SYNTAX)
    kept: list[str] = []
    for tok in tokenize(text, ops, spans):
        if not tok.text.strip():
            continue
        if tok.masked and (
            tok.text.startswith("//") or "/*" in tok.text
        ):
            continue  # 注释 trivia（GCC -E 输出会删）
        kept.append(tok.text)
    return kept


def _strip_marks(text: str) -> str:
    """去掉指令行 marker（行注释形态），保留其余文本（含换行）。"""
    return "\n".join(
        ln for ln in text.split("\n") if not _MARKS.fullmatch(ln)
    )


def _assert_tokens(src: str, expected: str, pack: str = PACK) -> None:
    out, _regions, _lm, _clean = _expand(src, pack)
    actual = _tokens(_strip_marks(out))
    want = _tokens(expected)
    assert actual == want, f"\n实际 token: {actual}\n期望 token: {want}\n输出:\n{out}"


# ── 判据（改前红）─────────────────────────────────────────────


def test_arguments_span_two_lines() -> None:
    """`F(1,` + 下一行 `2)` ⇒ `1+2`（GCC `1 +2`）。"""
    _assert_tokens(
        "#define F(a,b) a+b\nint r = F(1,\n            2);\n", "int r = 1+2;"
    )


def test_mixed_line_splice_and_cross_line_call() -> None:
    """同行既有普通 splice 宏又有跨行调用（审计 C1）：两个都展开、区域各一条。"""
    src = "#define M 9\n#define F(a,b) a+b\nint r = M + F(1,\n 2);\n"
    _assert_tokens(src, "int r = 9 + 1+2;")
    _out, regions, _lm, _clean = _expand(src)
    assert [r["name"] for r in regions] == ["M", "F"]


def test_mixed_line_multiple_splices_before_cross_line() -> None:
    src = "#define M 9\n#define N 3\n#define F(a,b) a+b\nint r = M + N + F(1,\n 2);\n"
    _assert_tokens(src, "int r = 9 + 3 + 1+2;")


def test_splice_macro_after_cross_line_call() -> None:
    """跨行调用在前、尾行还有普通 splice 宏（跨行只吃闭括号前文本）。"""
    src = "#define M 9\n#define F(a,b) a+b\nint r = F(1,\n 2) + M;\n"
    _assert_tokens(src, "int r = 1+2 + 9;")


def test_block_comment_argument_across_lines() -> None:
    """实参内含跨行块注释：展开文本保留注释 trivia，token 序列与 GCC 一致。"""
    _assert_tokens(
        "#define F(a,b) a+b\nint r = F(1, /* c\n d */ 2);\n", "int r = 1+2;"
    )


def test_name_and_paren_span_lines() -> None:
    """函数宏名与实参开括号跨行（`F` + 换行 + `(2)`）——换行是预处理空白。"""
    _assert_tokens("#define F(a) a+1\nint r = F\n(2);\n", "int r = 2+1;")


def test_arguments_span_three_lines() -> None:
    _assert_tokens(
        "#define F(a,b,c) a+b+c\nint r = F(1,\n 2,\n 3);\n", "int r = 1+2+3;"
    )


def test_trailing_tokens_after_close_paren_survive() -> None:
    """闭括号后的 token 留在尾行（换行 = 空白，语义不变）。"""
    _assert_tokens(
        "#define F(a,b) a+b\nint r = F(1,\n 2) + x;\n", "int r = 1+2 + x;"
    )


def test_nested_parenthesized_argument_across_lines() -> None:
    _assert_tokens(
        "#define F(a,b) a+b\nint r = F((1,\n 2), 3);\n", "int r = (1,2)+3;"
    )


def test_hash_variadic_across_lines() -> None:
    """`#__VA_ARGS__` 跨行实参：空白折成单空格（GCC `"1, 2"`）。"""
    _assert_tokens(
        "#define S(...) #__VA_ARGS__\nconst char *p = S(1,\n 2);\n",
        'const char *p = "1, 2";',
    )


def test_verilog_splice_macro_across_lines() -> None:
    """verilog 非空体宏（splice 处置）同样支持跨行（语言无关，测试用声明前缀形态）。"""
    _assert_tokens(
        "`define F(a,b) a+b\nassign r = `F(1,\n 2);\n",
        "assign r = 1+2;",
        _VPACK,
    )


# ── 回归守卫（改前绿；破坏不变式的坏实现会让它红）──────────────


def test_unbalanced_call_stays_unexpanded() -> None:
    """未配平（到文件尾仍无闭括号）⇒ 原样保留（既有边界，不把整文件拼进来）。"""
    src = "#define F(a,b) a+b\nint r = F(1,\n 2;\n"
    _assert_tokens(src, "int r = F(1, 2;")


def test_name_followed_by_non_paren_token_stays_unexpanded() -> None:
    """名字后第一个显著 token 不是 `(` ⇒ 不是调用（坏实现：无限向后拼行）。"""
    src = "#define F(a) a+1\nint r = F\nx = (2);\n"
    _assert_tokens(src, "int r = F x = (2);")


def test_cross_line_call_not_expanded_under_non_splice_policy(monkeypatch) -> None:
    """跨行调用只在 splice 处置下展开；line/inline（如 verilog 空体宏）保持旧行为。

    引擎测试不加载语言包插件（默认策略 = splice）⇒ 用注入策略固定 line/inline
    分支（生产侧 verilog 空体宏走 line/inline，见 `macro_policy/_policy.py`）。
    """
    import preprocessor._expand as expand_mod

    monkeypatch.setattr(
        expand_mod, "plan_macro", lambda policy, site: {"mode": "inline"}
    )
    src = "`define E(a)\n`E(1,\n 2) reg x;\n"
    out, _regions, _lm, _clean = _expand(src, _VPACK)
    assert _tokens(_strip_marks(out)) == _tokens("`E(1, 2) reg x;")


def test_lookahead_limit_keeps_unclosed_call_raw() -> None:
    """前限上限（256 行 / 8192 字符）外仍未闭合 ⇒ 不展开、不部分消费（登记边界）。"""
    lines = ["#define F(a,b) a+b", "int r = F(1,"]
    lines += ["  "] * 300
    lines.append("2);")
    src = "\n".join(lines) + "\n"
    _assert_tokens(src, "int r = F(1, 2);")


def test_lookahead_early_exit_is_linear() -> None:
    """性能守卫（审计 C2）：N 行"函数宏名裸用"不得逐行向后拼全文（二次代价）。

    HEAD 无跨行支持时 200 行 ~22ms；二次实现实测 200 行 ~60s。阈值 2s 留足
    CI 波动余量、仍能抓住二次回归。
    """
    import time

    src = "#define F(a,b) a+b\n" + "int v; F\n" * 200
    start = time.perf_counter()
    _expand(src)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"跨行前瞻疑似二次代价：200 行 {elapsed:.2f}s"


# ── 行映射 / 区域（机制复用判据）──────────────────────────────


def test_line_map_keeps_line_count_and_identity() -> None:
    """行数不变 ⇒ `out_to_src` 长度 = clean 行数、逐行恒等（宏体无换行时）。"""
    out, _regions, line_map, clean = _expand(
        "#define F(a,b) a+b\nint r = F(1,\n            2);\n"
    )
    assert line_map == list(range(1, len(clean.split("\n")) + 1))
    assert out.count("\n") == clean.count("\n")


def test_line_map_invariant_counts_body_newlines() -> None:
    """正确不变式（审计 E2）：`len(out_to_src) == clean 行数 + Σ 宏体换行`。

    宏体可因实参里的跨行块注释含 `\\n` ⇒ 输出行数按既有 splice 口径增加；
    新增行映射到**调用起始行**（与单行 splice 多行体同口径）。
    """
    _out, regions, line_map, clean = _expand(
        "#define F(a,b) a+b\nint r = F(1, /* c\n d */ 2);\n"
    )
    body_lines = sum(r["body"].count("\n") for r in regions)
    assert body_lines == 1
    assert len(line_map) == len(clean.split("\n")) + body_lines
    # 新增行（第 3 输出行）映射到调用首行（clean 第 2 行）
    assert line_map[2] == 2


def test_region_covers_multiline_source_and_body_slice() -> None:
    """区域：source_text = 完整跨行调用原文；展开切片 = 宏体。"""
    out, regions, _lm, _clean = _expand(
        "#define F(a,b) a+b\nint r = F(1,\n            2);\n"
    )
    assert len(regions) == 1
    reg = regions[0]
    assert reg["name"] == "F"
    assert reg["source_text"] == "F(1,\n            2)"
    assert reg["src_end_line"] == 3 and reg["src_end_col"] == 13
    assert out[reg["offset"] : reg["end_offset"]] == "1+2"


def test_text_after_close_paren_maps_to_its_own_line() -> None:
    """尾行文本仍在自己的源行：`+ x;` 位于第 3 源行（第 3 输出行）。"""
    out, _regions, _lm, _clean = _expand(
        "#define F(a,b) a+b\nint r = F(1,\n 2) + x;\n"
    )
    lines = out.split("\n")
    assert "+ x;" in lines[2]
    assert "1+2" in lines[1]


def test_pipeline_output_preserves_cross_line_call_tokens() -> None:
    """渲染面：splice 原文回插（多行 source_text）后 token 序列与输入一致（C 包）。

    行结构**不保证**逐字保留：闭括号后的尾随 token 可能被排到新行（见下一条
    登记边界）；判据 = token 序列（内容级保真）而非逐行相等。
    """
    from pipeline import run_pipeline_on_source

    src = "#define F(a,b) a+b\nint r = F(1,\n            2);\n"
    r = run_pipeline_on_source(
        src, rules_dir=PACK, ext_dirs=["grammar/c/plugins"], expand_macros=True,
        quiet=True,
    )
    assert not r.get("error"), r.get("error")
    assert _tokens(str(r.get("output") or "")) == _tokens(src)


def test_pipeline_trailing_token_after_cross_line_call() -> None:
    """登记边界（审计 E3）：闭括号后 token 在渲染面可能被排到新行——token 保真即可。"""
    from pipeline import run_pipeline_on_source

    src = "#define F(a,b) a+b\nint r = F(1,\n 2) + 3;\n"
    r = run_pipeline_on_source(
        src, rules_dir=PACK, ext_dirs=["grammar/c/plugins"], expand_macros=True,
        quiet=True,
    )
    assert not r.get("error"), r.get("error")
    assert _tokens(str(r.get("output") or "")) == _tokens(src)
