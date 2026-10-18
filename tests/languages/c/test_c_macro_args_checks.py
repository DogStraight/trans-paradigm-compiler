"""tests/languages/c/test_c_macro_args_checks.py — C 函数宏实参个数（MAC001）判据。

被测：`grammar/c/plugins/checks/macro_args/`（作者 2026-10-17 定：**语义级走插件侧
check 族**）——`tpc.toml` 声明 `[[analyzer.postpasses]]` + **`ast_optional = true`**；
规则数据 `rules/macro_args.toml`（条款原文 A 档）；判定 `rules/_macro_args_check.py`
（输入 = 引擎注入的展开期事实 `CTX_MACRO_INVOCATIONS`）。

**生产同路**：`ProjectChecker`（= `tpc check` 的执行入口，`main.py::_cmd_check`）。
关键判据（对应 TODO A2 ①）：
  1. **实参不足**（`#define F(a,b) a+b` + `F(1)`）——展开结果 `1+` 使解析失败，
     但 MAC001 **仍要报**（`ast_optional` 让事实型 postpass 在 `ast is None` 时执行）；
  2. 实参多余（`F(1,2,3)`）展开后语法合法、此前**静默** ⇒ 现在报；
  3. 零形参宏被传参（`Z(2)`）、变参宏缺具名实参（`W(a,b,...)` + `W(1)`）⇒ 报；
  4. 合法形态零误报：`Z()` / `Z( )` / `Z(/*c*/)` / `O()` / `F(1,2)` / 变参恰好具名；
  5. 位置 = **原始源坐标**（条件块压缩导致 clean/raw 行号不同的用例必须对）；
  6. 用户配置关闭规则（`enabled_rules=[]`）⇒ 不报；
  7. 已声明边界：`#if 0` 内调用、跨行实参调用不报（守卫当前行为）。

条款原文与 GCC 16.1 逐档对拍见 `rules/macro_args.toml` 头注。
Doc: `grammar/c/README.md`「宏实参个数（MAC）」
"""

import os

import pytest

from analyzer.checker import ProjectChecker
from core.config_registry import ConfigRegistry

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")


@pytest.fixture(scope="module")
def c_check(config_loaded):
    """C 包（含 checks 组件）；结束恢复 verilog（语言作用域是全局态）。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _run(tmp_path, src: str, *, enabled_rules=None) -> dict:
    """写样例 → `ProjectChecker.check`（= `tpc check` 生产路）→ report。"""
    path = tmp_path / "sample.c"
    path.write_text(src, encoding="utf-8")
    checker = ProjectChecker(rules_dir=_RULES, enabled_rules=enabled_rules)
    report = checker.check(str(path))
    return report["files"][0]


def _codes(fr: dict) -> list[str]:
    return [d["code"] for d in fr["semantic"]]


def _mac_diags(fr: dict) -> list[dict]:
    return [d for d in fr["semantic"] if d["code"] == "MAC001"]


# ── 核心缺陷面：少给 / 多给 / 零参 / 变参缺具名 ───────────────


def test_too_few_args_reported_even_when_parse_fails(tmp_path, c_check) -> None:
    """`F(1)` 展开成 `1+` ⇒ parse 失败；MAC001 仍须报（ast_optional 的直接判据）。"""
    fr = _run(tmp_path, "#define F(a, b) a + b\nint x = F(1);\n")
    assert fr["parse_ok"] is False  # 展开结果语法非法（次生错误照旧）
    diags = _mac_diags(fr)
    assert len(diags) == 1
    assert "形参 2" in diags[0]["message"] and "实参 1" in diags[0]["message"]
    assert diags[0]["level"] == "warning"


def test_too_many_args_reported(tmp_path, c_check) -> None:
    """多余实参此前被静默丢弃（展开后语法合法）——现在报。"""
    fr = _run(tmp_path, "#define F(a, b) a + b\nint x = F(1, 2, 3);\n")
    assert fr["parse_ok"] is True and not fr["syntax"]
    diags = _mac_diags(fr)
    assert len(diags) == 1
    assert "形参 2" in diags[0]["message"] and "实参 3" in diags[0]["message"]


def test_zero_param_macro_called_with_argument(tmp_path, c_check) -> None:
    fr = _run(tmp_path, "#define Z() 1\nint x = Z(2);\n")
    assert fr["parse_ok"] is True
    diags = _mac_diags(fr)
    assert len(diags) == 1
    assert "形参 0" in diags[0]["message"]


def test_variadic_missing_named_args_reported(tmp_path, c_check) -> None:
    """`W(a,b,...)` + `W(1)` / `W()`：缺具名实参，GCC 全档硬错。"""
    fr = _run(
        tmp_path,
        "#define W(a, b, ...) a + b\nint x = W(1);\nint y = W();\n",
    )
    assert len(_mac_diags(fr)) == 2


# ── 合法形态零误报 ─────────────────────────────────────────


LEGAL = """#define F(a, b) a + b
#define Z() 1
#define O(a) a
#define W(a, b, ...) a + b
#define V(...) f(__VA_ARGS__)
int a = F(1, 2);
int b = Z();
int c = Z( );
int d = Z(/* comment */);
int e = W(1, 2);
int g = W(1, 2, 3);
int h = V();
int i = V(1, 2);
void use(void) { O(); O(/* comment */); F(1, 2); }
"""


def test_legal_forms_not_reported(tmp_path, c_check) -> None:
    """合法形态（空实参 / 注释实参 / 变参恰好具名）零误报。"""
    fr = _run(tmp_path, LEGAL)
    assert fr["parse_ok"] is True
    assert _mac_diags(fr) == []


def test_variadic_exact_named_not_reported(tmp_path, c_check) -> None:
    """已声明边界：`V(a,...)` + `V(1)` 是 C99-C17 pedantic 级、C23 起接受 ⇒ 不报。"""
    fr = _run(tmp_path, "#define V(a, ...) a\nint x = V(1);\n")
    assert fr["parse_ok"] is True
    assert _mac_diags(fr) == []


# ── 位置：原始源坐标（clean/raw 行号不同）───────────────


def test_position_is_original_source_line(tmp_path, c_check) -> None:
    """`#if 0` 块压缩使 clean 行号 < 原始行号：诊断仍须指原始源行 5。"""
    src = (
        "#define F(a, b) a + b\n"   # 1
        "#if 0\n"                    # 2
        "int dead;\n"                # 3
        "#endif\n"                   # 4
        "int x = F(1, 2, 3);\n"      # 5
    )
    fr = _run(tmp_path, src)
    diags = _mac_diags(fr)
    assert len(diags) == 1
    start = diags[0]["range"]["start"]
    assert start["line"] + 1 == 5  # LSP 0-based → 原始源第 5 行
    assert start["character"] == 8  # `int x = F` 的 F 起列


# ── 规则激活（用户配置面）──────────────────────────────────


def test_rule_can_be_disabled(tmp_path, c_check) -> None:
    """`enabled_rules=[]`（= 用户配置 enabled 空集）⇒ 不报。"""
    fr = _run(
        tmp_path,
        "#define F(a, b) a + b\nint x = F(1, 2, 3);\n",
        enabled_rules=[],
    )
    assert _codes(fr) == []


def test_default_rule_is_active(tmp_path, c_check) -> None:
    """`default = true`（A 档）⇒ 不注入启用集时 MAC001 生效。"""
    fr = _run(tmp_path, "#define F(a, b) a + b\nint x = F(1, 2, 3);\n")
    assert _codes(fr) == ["MAC001"]


# ── 已声明边界（守卫当前行为）─────────────────────────────


def test_macro_from_included_header_is_checked(tmp_path, c_check) -> None:
    """头文件里的宏在本文件调用：宏表来自 include 扫描 ⇒ 检查照常生效。"""
    (tmp_path / "h.h").write_text("#define F(a, b) a + b\n", encoding="utf-8")
    fr = _run(tmp_path, '#include "h.h"\nint x = F(1, 2, 3);\n')
    diags = _mac_diags(fr)
    assert len(diags) == 1
    assert diags[0]["range"]["start"]["line"] + 1 == 2  # 本文件第 2 行


def test_call_inside_included_header_not_reported(tmp_path, c_check) -> None:
    """边界：被包含内容里的调用点没有本文件坐标（clean_to_raw=None）⇒ 丢弃不猜。"""
    (tmp_path / "h.h").write_text(
        "#define F(a, b) a + b\nint bad = F(1);\n", encoding="utf-8"
    )
    fr = _run(tmp_path, '#include "h.h"\nint ok = 0;\n')
    assert _mac_diags(fr) == []


# ── 定义时间线（顺序语义；审计反例修复）────────────────────


def test_macro_defined_after_call_is_not_a_macro_call(tmp_path, c_check) -> None:
    """后置定义：`int F(int);` + `F(1)` 在 `#define F(a,b)` 之前 ⇒ 不是宏调用、不报。

    （展开器仍按最终宏表展开该行——既有近似；但**检查**按定义时间线判，不误报。）
    """
    src = "int F(int);\nint main(void) { return F(1); }\n#define F(a, b) a + b\n"
    fr = _run(tmp_path, src)
    assert _mac_diags(fr) == []


def test_redefinition_uses_each_call_time_params(tmp_path, c_check) -> None:
    """重定义前后各按**当时**形参表判；只有重定义后那处错给 MAC001。"""
    src = (
        "#define F(a) a\n"
        "int x = F(1);\n"          # 1 形参 ⇒ 合法
        "#undef F\n"
        "#define F(a, b) a + b\n"
        "int y = F(1, 2);\n"       # 2 形参 ⇒ 合法
        "int z = F(3);\n"          # 2 形参、1 实参 ⇒ 报
    )
    fr = _run(tmp_path, src)
    diags = _mac_diags(fr)
    assert len(diags) == 1
    assert diags[0]["range"]["start"]["line"] + 1 == 6


def test_undef_before_call_is_not_a_macro_call(tmp_path, c_check) -> None:
    fr = _run(tmp_path, "#define F(a, b) a + b\n#undef F\nint x = F(1);\n")
    assert _mac_diags(fr) == []


def test_undef_after_call_is_a_known_boundary(tmp_path, c_check) -> None:
    """已声明边界：`#undef` **之前**的调用点（展开器用最终宏表 ⇒ 根本不展开）
    没有事实 ⇒ 不报（GCC 会报；属展开器既有近似，登记不修）。"""
    fr = _run(tmp_path, "#define F(a, b) a + b\nint x = F(1);\n#undef F\n")
    assert _mac_diags(fr) == []


def test_backslash_continuation_segment_not_reported(tmp_path, c_check) -> None:
    """已声明边界：行拼接段内的调用点行列不可靠 ⇒ 丢弃不报（守卫当前行为）。"""
    fr = _run(
        tmp_path,
        "#define F(a, b) a + b\nint x = 1 + \\\n        F(1);\n",
    )
    assert _mac_diags(fr) == []


# ── 豁免注释（parse 失败文件的语义诊断同样可豁免）──────────


def test_suppression_applies_to_semantic_on_parse_failed_file(tmp_path, c_check) -> None:
    """`disable-line` 对 too-few（parse 失败）的 MAC001 生效；语法诊断不被豁免掩盖。"""
    from main import _apply_check_suppressions

    path = tmp_path / "s.c"
    path.write_text(
        "#define F(a, b) a + b\n"
        "int x = F(1); // tpc-check: disable-line MAC001\n",
        encoding="utf-8",
    )
    report = ProjectChecker(rules_dir=_RULES).check(str(path))
    fr = report["files"][0]
    assert fr["parse_ok"] is False
    assert _mac_diags(fr)  # 豁免前有
    _apply_check_suppressions(report, _RULES)
    assert _mac_diags(fr) == []  # 语义诊断被豁免
    assert fr["syntax"]  # 语法诊断仍在（parse_error 不掩盖）


def test_call_in_inactive_branch_not_reported(tmp_path, c_check) -> None:
    """`#if 0` 分支在扫描期被压缩 ⇒ 不展开、无事实 ⇒ 不报。"""
    src = (
        "#define F(a, b) a + b\n"
        "#if 0\n"
        "int dead = F(1);\n"
        "#endif\n"
        "int live = F(1, 2);\n"
    )
    fr = _run(tmp_path, src)
    assert _mac_diags(fr) == []


def test_multiline_call_not_reported(tmp_path, c_check) -> None:
    """已声明边界（A1 ②）：实参跨行的调用不展开 ⇒ 无事实可检（守卫当前行为）。"""
    fr = _run(
        tmp_path,
        "#define F(a, b) a + b\nint x = F(1,\n            2);\n",
    )
    assert _mac_diags(fr) == []
