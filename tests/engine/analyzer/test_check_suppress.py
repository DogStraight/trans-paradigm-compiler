"""suppress.py 测试：tpc-check 豁免注释（区间对 + disable-line）的输出层过滤。

单测覆盖 build_suppress_map（区间/单行/规则集/未闭合/on 行边界/同行合并）与
apply_suppressions（code 匹配/无 range 保留/空表）；集成冒烟：豁免注释本身
不破坏 ProjectChecker 解析，check + apply 全流程可跑。

Doc: docs/references.md（Verilog 静态检查工具群：suppress 借鉴 Verilator lint_off/lint_on）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.suppress import apply_suppressions, build_suppress_map
from lexer.comment_syntax import load_comment_syntax


_VERILOG = "grammar/verilog"


def _smap(text: str):
    """豁免扫描 + 语言包注释形态（verilog：`//` 与 `/* */` 来自声明）。"""
    return build_suppress_map(text, load_comment_syntax(_VERILOG))


# ── build_suppress_map：区间豁免 ───────────────────────────────────────────

def test_interval_pair():
    text = (
        "module m;\n"
        "  /* tpc-check off WC001 */\n"   # 行 1 豁免 WC001
        "  assign x = y;\n"                # 行 2 豁免
        "  /* tpc-check on */\n"           # 行 3 恢复（本身不豁免）
        "  assign z = w;\n"                # 行 4 不豁免
        "endmodule\n"
    )
    m = _smap(text)
    assert m.get(1) == {"WC001"}     # off 行豁免 WC001
    assert m.get(2) == {"WC001"}     # 区间内
    assert 3 not in m                # on 行不豁免
    assert 4 not in m


def test_interval_rules_subset():
    text = (
        "/* tpc-check off WC001 N001 */\n"   # 行 0
        "/* tpc-check on */\n"                # 行 1
    )
    m = _smap(text)
    assert m.get(0) == {"WC001", "N001"}


def test_unclosed_off_goes_to_eof():
    text = "/* tpc-check off */\na\nb\nc\n"
    m = _smap(text)
    assert m.get(0) is None
    assert m.get(1) is None
    assert m.get(2) is None
    assert m.get(3) is None


def test_on_without_off_ignored():
    text = "/* tpc-check on */\nx\n"
    m = _smap(text)
    assert m == {}


# ── build_suppress_map：单行豁免 ───────────────────────────────────────────

def test_disable_line():
    text = (
        "module m;\n"
        "  // tpc-check: disable-line N001\n"   # 行 1
        "  assign x = y;\n"                      # 行 2 不豁免
        "endmodule\n"
    )
    m = _smap(text)
    assert m.get(1) == {"N001"}
    assert 2 not in m


def test_disable_line_all_rules():
    text = "// tpc-check: disable-line\nx\n"
    m = _smap(text)
    assert m.get(0) is None


def test_interval_and_line_merge():
    text = (
        "/* tpc-check off WC001 */\n"          # 行 0 区间 WC001
        "// tpc-check: disable-line N001\n"    # 行 1 单行 N001
        "/* tpc-check on */\n"
    )
    m = _smap(text)
    assert m.get(0) == {"WC001"}
    # 行 1 合并：区间 WC001 + 单行 N001
    assert m.get(1) == {"WC001", "N001"}


def test_off_inside_comment_not_triggered():
    # 普通注释里提到 tpc-check 字样但不构成指令 → 不豁免
    text = "// 讨论 /* tpc-check off */ 的用法\nx\n"
    m = _smap(text)
    assert m == {}


# ── 声明驱动：豁免指令的注释标点随语言包变 ─────────────────────────────────

def test_yaml_hash_forms():
    """yaml 用 `#`：单行豁免写法全靠声明（引擎不认识 `//`）。"""
    syntax = load_comment_syntax("grammar/yaml")
    text = (
        "# tpc-check: disable-line N001\n"   # 行 0：单行豁免（行注释形态）
        "a: 1\n"                              # 行 1：不豁免
    )
    m = build_suppress_map(text, syntax)
    assert m == {0: {"N001"}}


def test_yaml_line_comment_interval_not_recognized():
    """区间豁免需**块注释**声明：yaml 只有行注释 → 该形态不存在。

    行注释里的 `off` 文本属于注释区（不构成指令）——若认定的话，普通注释里
    提到该字样就会误触发（verilog 侧同款守卫，见
    `test_off_inside_comment_not_triggered`）。
    """
    syntax = load_comment_syntax("grammar/yaml")
    text = "# tpc-check off WC001\na: 1\n"
    assert build_suppress_map(text, syntax) == {}


def test_verilog_forms_not_matched_under_yaml():
    """verilog 形态的指令在 yaml 注释标点下不是注释，自然不构成指令。"""
    syntax = load_comment_syntax("grammar/yaml")
    text = "// tpc-check: disable-line N001\n"
    assert build_suppress_map(text, syntax) == {}


def test_no_block_comment_language_has_no_interval_form():
    """未声明块注释的语言包（yaml）→ 区间豁免形态不存在（不报错）。"""
    syntax = load_comment_syntax("grammar/yaml")
    text = "/* tpc-check off WC001 */\n"
    assert build_suppress_map(text, syntax) == {}


# ── apply_suppressions ─────────────────────────────────────────────────────

def _diag(line: int, code: str) -> dict:
    return {
        "stage": "semantic",
        "code": code,
        "message": "x",
        "range": {
            "start": {"line": line, "character": 0},
            "end": {"line": line, "character": 1},
        },
    }


def test_apply_filters_matching_code():
    diags = [_diag(1, "WC001"), _diag(1, "N001"), _diag(2, "WC001")]
    m = {1: {"WC001"}}
    kept = apply_suppressions(diags, m)
    assert [d["code"] for d in kept] == ["N001", "WC001"]


def test_apply_all_rules_none():
    diags = [_diag(1, "WC001"), _diag(1, "N001")]
    m = {1: None}
    assert apply_suppressions(diags, m) == []


def test_apply_no_range_kept():
    d = {"stage": "syntax", "code": "parse-error", "message": "x", "range": None}
    m = {0: None}
    assert apply_suppressions([d], m) == [d]


def test_apply_empty_map_identity():
    diags = [_diag(1, "WC001")]
    assert apply_suppressions(diags, {}) == diags


# ── 集成冒烟：豁免注释不破坏解析 ───────────────────────────────────────────

def test_check_pipeline_with_suppress_comments(tmp_path):
    from analyzer.checker import ProjectChecker
    from analyzer.suppress import apply_suppressions

    src = (
        "module m;\n"
        "  /* tpc-check off WC001 */\n"
        "  wire a;\n"
        "  /* tpc-check on */\n"
        "  // tpc-check: disable-line N001\n"
        "  assign a = 1'b0;\n"
        "endmodule\n"
    )
    f = tmp_path / "m.sv"
    f.write_text(src, encoding="utf-8")
    checker = ProjectChecker(rules_dir="grammar/verilog")
    report = checker.check(str(f))
    # 豁免注释本身不产生语法诊断
    assert report["files"][0]["parse_ok"]
    # 全流程可跑：build + apply（输出层，不改变 report 形状）
    f0 = report["files"][0]
    smap = _smap(src)
    f0["syntax"] = apply_suppressions(f0["syntax"], smap)
    f0["semantic"] = apply_suppressions(f0["semantic"], smap)
    assert set(f0) >= {"path", "parse_ok", "parse_error", "syntax", "semantic"}
