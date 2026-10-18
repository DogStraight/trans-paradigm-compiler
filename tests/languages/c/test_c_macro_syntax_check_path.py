"""tests/languages/c/test_c_macro_syntax_check_path.py — `tpc check` 语法阶段的
**原始源宏定义形式语法**面（A2 ②，两路径统一）。

缺陷（已修）：`tpc lint` 报宏定义形式错误（`#define` 的宏名/形参表/宏体算子）rc=1，
但 `tpc check` 仍「No issues found」rc=0——因为 check 的语法阶段 lint 的是**展开后**
文本，而 `#define` 定义行在扫指令时已被消费。修法 = `FilePipeline` 语法阶段在**原始源**
上再跑一次同一函数（`linter/macro_syntax.py`），与 `tpc lint` **同实现、同判定**；
语言包未声明 `[macro_syntax]`（verilog）⇒ 返回空、零变化。

判据：
  1. 四类形式错（宏名 / 形参表空项 / 形参表未闭合 / 宏体算子）⇒ check 语法阶段各报一条
     **blocking** 诊断，code/位置与 `macro_syntax_diagnostics(原文)` 完全一致（两路径同源）；
  2. 未闭合形参表此前在 check 路径**抛 ConfigError 崩栈**（展开期 fail-fast 冒泡）⇒
     现在给受控诊断、不异常；
  3. 合法宏定义零误报、正常解析；
  4. 混合文件（宏定义合法 + 代码有语法错）仍走展开文本 lint（早退只发生在宏定义形式错）；
  5. verilog 不接线（同一函数在 `test_macro_syntax_checks.py` 已有声明面门禁，这里从
     check 路径复证一次——避免"绕过声明"的回归）。

Doc: `grammar/c/README.md`「预处理面」/ `analyzer/structure.py::raw_source_macro_diags`
"""

import os

import pytest

from analyzer.checker import ProjectChecker
from core.config_registry import ConfigRegistry
from linter.macro_syntax import macro_syntax_diagnostics

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

#: 形式错样本 ⇒ 期望 (code, 1-based 行, 0-based 列)
MALFORMED: dict[str, tuple[str, str, int, int]] = {
    "宏名缺失": ("#define\nint x = 0;\n", "macro-name", 1, 7),
    "形参表空项": ("#define F(a,) a\nint x = 0;\n", "macro-param", 1, 12),
    "形参表未闭合": ("#define G(a, b\nint x = 0;\n", "macro-param", 1, 9),
    "宏体字符串化非形参": ("#define S(a) # b\nint x = 0;\n", "macro-body", 1, 13),
}


@pytest.fixture(scope="module")
def c_check(config_loaded):
    """C 包（语法阶段接原始源宏语法检查）；结束恢复 verilog。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _check(tmp_path, src: str) -> tuple[dict, dict]:
    path = tmp_path / "sample.c"
    path.write_text(src, encoding="utf-8")
    report = ProjectChecker(rules_dir=_RULES).check(str(path))
    return report, report["files"][0]


def _syntax_triples(fr: dict) -> list[tuple]:
    return [
        (d["code"], d["range"]["start"]["line"] + 1, d["range"]["start"]["character"])
        for d in fr["syntax"]
        if d.get("range")
    ]


# ── 1. 四类形式错：报 + 与 linter 同源 ────────────────────


@pytest.mark.parametrize("src,code,line,col", list(MALFORMED.values()), ids=list(MALFORMED))
def test_malformed_define_reported_in_check(
    tmp_path, c_check, src: str, code: str, line: int, col: int
) -> None:
    report, fr = _check(tmp_path, src)
    assert report["exit_code"] == 1
    assert fr["parse_ok"] is False  # 语法阶段阻断
    assert (code, line, col) in _syntax_triples(fr)


def test_check_path_matches_linter_function(tmp_path, c_check) -> None:
    """两路径同源：check 语法阶段的宏语法诊断 == `macro_syntax_diagnostics(原文)`。"""
    for src, *_expected in MALFORMED.values():
        direct = [
            (d.code, d.range[0].line + 1, d.range[0].character)
            for d in macro_syntax_diagnostics(src, _RULES)
        ]
        _, fr = _check(tmp_path, src)
        assert _syntax_triples(fr) == direct


# ── 2. 未闭合形参表：受控诊断、不崩栈 ─────────────────────


def test_unclosed_param_is_controlled_not_crash(tmp_path, c_check) -> None:
    """此前 check 路径在该输入上抛 `ConfigError`（展开期 fail-fast 冒泡）⇒ 现在受控。"""
    report, fr = _check(tmp_path, "#define G(a, b\n")
    assert report["exit_code"] == 1
    assert [d["code"] for d in fr["syntax"]] == ["macro-param"]
    assert "未闭合" in fr["syntax"][0]["message"]


# ── 3. 合法定义零误报 ─────────────────────────────────────


VALID = "#define F(a, b) ((a) + (b))\n#define N 4\nint x = F(1, 2) + N;\n"


def test_valid_macro_definition_not_reported(tmp_path, c_check) -> None:
    report, fr = _check(tmp_path, VALID)
    assert report["exit_code"] == 0
    assert fr["parse_ok"] is True
    assert fr["syntax"] == []
    assert fr["semantic"] == []


# ── 4. 混合文件：早退只在宏定义形式错时发生 ────────────────


def test_mixed_file_keeps_expanded_lint_diags(tmp_path, c_check) -> None:
    """宏定义合法 + 代码语法错 ⇒ 仍走展开文本 lint（phase-statement），不只报宏面。"""
    src = "#define F(a, b) ((a) + (b))\nint ok = F(1, 2);\nvoid g(void) { a + ; }\n"
    _, fr = _check(tmp_path, src)
    codes = {d["code"] for d in fr["syntax"]}
    assert "phase-statement" in codes
    assert not any(c.startswith("macro-") for c in codes)


# ── 5. verilog 不接线（声明面门禁从 check 路径复证）───────


def test_verilog_check_path_not_wired(tmp_path, config_loaded) -> None:
    """verilog 未声明 `[macro_syntax]` ⇒ check 路径不产生宏语法诊断（零变化）。"""
    del config_loaded
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )
    try:
        path = tmp_path / "s.sv"
        path.write_text("`define F(a,) a\nmodule m;\n  wire a;\nendmodule\n", encoding="utf-8")
        report = ProjectChecker(rules_dir="grammar/verilog").check(str(path))
        codes = {d["code"] for f in report["files"] for d in f["syntax"]}
        assert not any(str(c).startswith("macro-") for c in codes)
    finally:
        ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    # 函数面同样为空（声明驱动的单一判据）
    assert macro_syntax_diagnostics("`define F(a,) a\n", "grammar/verilog") == []
