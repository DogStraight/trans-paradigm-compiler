"""tests/languages/c/test_c_exit_criteria_negative.py — 退出判据 3：四类负样本各被拒。

判据 3 原文 = "作用域 / 链接 / 标签 / 函数原型的负样本各被拒"。本文件是**判据级汇总面**
（逐族细判据仍在各自文件：`test_c_storage_class_checks.py`、`test_c_label_checks.py`、
`test_c_raw_understanding.py`），每类给一条代表负样本 + 一条正样本，证明"该族确实有
判定、且不误报"。

## 口径（判据 3 的落地层级，与刻度块 7 对齐）

| 族 | 机制 | 说明 |
|---|---|---|
| 作用域 | analyzer raw 安全网 **E002**（`validate_raw_statement`：作用域/声明序/深度精确） | 遮蔽例 `typedef int t; void f(){ int t; x=(t)y; }` ⇒ 管线失败 + E002 |
| 链接 | **存储类约束族 CSC001–CSC012**（近似面） | C 链接性完整规则（§6.2.2 跨声明同/异链接性）= 阶段 3 的 **S2，已拍板"不采"**；负样本覆盖 = 存储类组合/位置约束族（如 `typedef static int x;`） |
| 标签 | **LAB001–LAB003**（postpass，warning） | 重复 label / 未定义 goto / case 无 switch |
| 函数原型 | **语法非法原型被拒**（linter/parser） | `int f(...);` 这类无参数变参原型是语法错；**原型一致性（跨声明类型一致）= S3，需类型模型，触发式搁置**（已登记，不属本判据活跃缺口） |

警告级（CSC/LAB）只报诊断、不阻断管线——本包 check 组件的既有口径；"被拒"= 诊断命中。
Doc: `PROGRESS.md`（退出判据 3）、`grammar/c/README.md`（CSC/LAB 组件节）
"""

import os

import pytest

from analyzer.traversal import AnalysisTraversal
from core.check_registry import get_check_rules
from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from pipeline import run_pipeline_on_source
from transform.normalizer import normalize_ast

from tests.languages.c.conftest import _lint
from tests.languages.c.test_c_label_checks import NEGATIVE as LAB_NEGATIVE
from tests.languages.c.test_c_label_checks import POSITIVE as LAB_POSITIVE
from tests.languages.c.test_c_storage_class_checks import NEGATIVE as CSC_NEGATIVE
from tests.languages.c.test_c_storage_class_checks import POSITIVE as CSC_POSITIVE

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")


def _run_pipeline(src: str) -> dict:
    return run_pipeline_on_source(
        source=src,
        input_path="case.c",
        out_dir=None,
        quiet=True,
        rules_dir=_RULES,
        ext_dirs=[_PLUGINS],
    )


def _all_check_ids() -> list[str]:
    return [str(r["id"]) for r in get_check_rules(plugins_dir=_PLUGINS)]


def _diagnostics(src: str) -> list:
    """解析 → normalize（生产口径）→ analyze（全部 check 规则强制启用）。"""
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    register = GrammarRulesRegister()
    rules = setup_grammar(_RULES, register, ext_dirs=[_PLUGINS])
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=_RULES, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=_RULES, ext_dirs=[_PLUGINS])
    ast = parser.parse(lexer.tokenize(src))
    assert ast is not None, f"语法层应宽进接受：{src!r}"
    at = AnalysisTraversal(rules, rules_dir=_RULES)
    at._checks_enabled = _all_check_ids()
    at.analyze(normalize_ast(ast))
    return list(at.diagnostics)


@pytest.fixture(autouse=True)
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


class TestScope:
    """作用域：raw 安全网 E002（遮蔽 / 声明序，作用域精确）。"""

    def test_shadowed_typedef_use_rejected(self):
        res = _run_pipeline("typedef int t;\nvoid f(void){ int t; x = (t)y; }\n")
        assert res.get("success") is False, "遮蔽例应被拒（不得静默接受）"
        assert "E002" in str(res.get("error")), res.get("error")

    def test_non_shadowed_cast_accepted(self):
        """正样本：无遮蔽的 typedef 强转语句闭环（不误报）。"""
        res = _run_pipeline("typedef int t;\nvoid f(void){ x = (t)y; }\n")
        assert res.get("success") is True and not res.get("error"), res.get("error")


class TestLinkage:
    """链接：存储类约束族（S2 完整链接性规则不采，近似面已登记）。"""

    @pytest.mark.parametrize(
        "case", ["typedef+static", "static+extern", "_Thread_local 用于函数"]
    )
    def test_storage_constraint_negative_reported(self, case):
        src, expected = CSC_NEGATIVE[case]
        codes = {str(d.code) for d in _diagnostics(src)}
        assert set(expected) <= codes, f"{case}: 期望 {expected}，实得 {codes}"

    def test_static_inline_function_not_reported(self):
        """正样本：头文件高频合法形态 `static inline int f(void){}` 不得误报。"""
        codes = {str(d.code) for d in _diagnostics(CSC_POSITIVE["static inline 函数（关键）"])}
        assert not {c for c in codes if c.startswith("CSC")}, codes


class TestLabels:
    """标签：LAB001–LAB003（重复 label / 未定义 goto / case 无 switch）。"""

    @pytest.mark.parametrize(
        "case", ["重复 label 两处", "未定义 goto", "case 无 switch"]
    )
    def test_label_negative_reported(self, case):
        src, code, count = LAB_NEGATIVE[case]
        codes = [str(d.code) for d in _diagnostics(src) if str(d.code).startswith("LAB")]
        assert codes == [code] * count, f"{case}: 期望 {code}×{count}，实得 {codes}"

    def test_cross_function_same_label_not_reported(self):
        """正样本：不同函数同名 label 合法（不得误报）。"""
        codes = [
            str(d.code)
            for d in _diagnostics(LAB_POSITIVE["不同函数同名 label"])
            if str(d.code).startswith("LAB")
        ]
        assert codes == [], codes


class TestPrototypeSyntax:
    """函数原型：语法非法原型被 linter 拒（一致性 = S3 触发式搁置，需类型模型）。"""

    @pytest.mark.parametrize(
        "src",
        ["int f(...);\n", "void f(...);\n"],
    )
    def test_invalid_prototype_syntax_rejected(self, c_linter, src):
        assert _lint(src, c_linter), f"{src!r}: 非法原型未被拒（语法宽进泄漏）"

    @pytest.mark.parametrize(
        "src",
        [
            "int f(void);\n",
            "int g(int, ...);\n",
            "int h();\n",
            "void k(void *, size_t);\n",
        ],
    )
    def test_valid_prototype_not_rejected(self, c_linter, src):
        assert _lint(src, c_linter) == [], f"{src!r}: 合法原型被误报"


class TestCriterion4PrototypeConsistencyBoundary:
    """S3 原型一致性（跨声明类型一致）——**触发式搁置**登记，不属判据 3 活跃缺口。

    需求类型模型（类型等价判断），与"解析前符号判定"同属后续专项；本类只锁"当前不做"
    的事实：不一致原型**不**被拒绝（避免有人误以为已覆盖）。
    """

    @pytest.mark.parametrize(
        "src",
        [
            "int f(int);\nfloat f(int);\n",  # 返回类型不一致
            "int f(int);\nint f(int, int);\n",  # 参数个数不一致
            "int f(void, int);\n",  # void 非唯一参数（§6.7.6.3 约束）
            "int f(void a);\n",  # void 带名参数
        ],
    )
    def test_inconsistent_or_void_constraints_not_yet_checked(self, c_linter, src):
        assert _lint(src, c_linter) == [], (
            "S3 原型一致性/void 参数约束若已落地，请把本类改为正向判据并更新 PROGRESS 块 7 口径"
        )
