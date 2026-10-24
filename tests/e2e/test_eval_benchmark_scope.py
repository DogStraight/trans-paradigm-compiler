"""tests/e2e/test_eval_benchmark_scope.py — 对拍口径：排除面只认 parse 失败。

被测：`tests/e2e/eval_benchmark.py::_tpc_diags_all` / `run` 的语义口径（块 10 末项）：

  · **parse 失败**（`parse_ok=False`）的工程不做对拍判定——0 诊断是假干净，
    部分诊断也不完整，故不进共识 / FP / 漏报统计；
  · 但事实型 postpass（`[[analyzer.postpasses]] ast_optional = true`，C 宏实参
    个数 MAC001）在 parse 失败文件上仍产出诊断，**不得静默丢弃**：进
    `row["facts"]` 与 `summary["tpc_facts"]`，标注"不参与对拍"；
  · **语法阶段 lint 诊断**（如 ST001 行尾空白）不构成排除——对拍比较的是
    semantic 阶段产物；此前 `or f.get("syntax")` 把 6/7 真实语料组误判为
    "不可对拍"（全部 parse_ok，仅带风格 lint）。

判据（改前红）：C `F(1)`（形参 2 / 实参 1）⇒ parse_ok False + MAC001，facts 断言
失败；verilog `wire unused_sig` + 行尾空白 ⇒ parse_ok True + ST001 + UN001，
diags 断言失败（旧口径把它排除）。
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
importlib.import_module("tests._bootstrap")  # noqa: E402

from analyzer.checker import ProjectChecker  # noqa: E402
from core.config_registry import ConfigRegistry  # noqa: E402
from tests.e2e import eval_benchmark  # noqa: E402

_C_RULES = "grammar/c"
_C_PLUGINS = os.path.join(_C_RULES, "plugins")
# 形参 2 / 实参 1 ⇒ 展开成 `1+` ⇒ parse 失败；MAC001 由 ast_optional 事实型
# postpass 在 parse 失败文件上产出（判据形态与 test_c_macro_args_checks 同源）。
_MAC_SRC = "#define F(a, b) a + b\nint x = F(1);\n"


@pytest.fixture()
def c_lang(config_loaded):
    """C 包（含 ast_optional postpass）；结束恢复 verilog（语言是全局态）。"""
    del config_loaded
    ConfigRegistry.load_language(_C_RULES, plugins_dir=_C_PLUGINS)
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _write(tmp_path) -> str:
    path = tmp_path / "sample.c"
    path.write_text(_MAC_SRC, encoding="utf-8")
    return str(path)


def test_parse_failed_facts_collected_not_compared(tmp_path, c_lang) -> None:
    """F(1) 少参 ⇒ parse 失败；MAC001 进 facts、diags 为空。"""
    checker = ProjectChecker(rules_dir=_C_RULES)
    diags, parse_ok, facts = eval_benchmark._tpc_diags_all(
        checker, [_write(tmp_path)]
    )
    assert parse_ok is False
    assert diags == []                       # 不可对拍：不进共识 / FP
    assert [f["code"] for f in facts] == ["MAC001"]
    assert facts[0]["file"] == "sample.c"
    assert facts[0]["line"] == 2


def test_parse_failed_row_and_summary_keep_facts(
    tmp_path, c_lang, monkeypatch
) -> None:
    """run() 的 TPC-PARSE-FAIL 行带 facts，汇总计数不吞。"""
    monkeypatch.setitem(
        eval_benchmark._ORACLES, "fake",
        (lambda files: ([], []), {}, set()),
    )
    checker = ProjectChecker(rules_dir=_C_RULES)
    group = {"name": "c_fact", "files": [_write(tmp_path)]}
    rows, summary = eval_benchmark.run(
        checker, [group], "test", oracles=["fake"]
    )
    row = rows[0]
    assert row["verdict"] == "TPC-PARSE-FAIL"
    assert [f["code"] for f in row["facts"]] == ["MAC001"]
    assert summary["tpc_parse_fail"] == 1
    assert summary["tpc_facts"] == 1


# verilog：行尾空白（ST001，语法阶段）+ 未使用声明（UN001，语义阶段）。
# parse_ok True、无阻断诊断 ⇒ 旧口径被 `or f.get("syntax")` 排除，新口径照常对拍。
_V_STYLE_SRC = "module t;\n  wire unused_sig;\n  \nendmodule\n"


def test_style_lint_diags_do_not_exclude(tmp_path, config_loaded) -> None:
    """ST001 行尾空白不构成对拍排除：语义诊断照常进入 diags。"""
    del config_loaded
    path = tmp_path / "style.v"
    path.write_text(_V_STYLE_SRC, encoding="utf-8")
    checker = ProjectChecker(rules_dir="grammar/verilog")
    diags, parse_ok, facts = eval_benchmark._tpc_diags_all(
        checker, [str(path)]
    )
    assert parse_ok is True
    assert facts == []
    assert [d["code"] for d in diags] == ["UN001"]
