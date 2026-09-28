"""tests/engine/analyzer/test_shared_components_wiring.py — 检查侧共享渲染器的**接线**判据。

`tpc check` 走 `analyzer/shared_components.py` 的独立组件装载（与 pipeline 侧刻意分离），
其中的 `Renderer` 必须与主管线同口径：接上语言包声明的行终止型注释词表
（`Lexer.line_terminating_comment_starts()`，来源 = 包内 `[comment] pairs` 的 `kind = line`）。

缺接线（缺省空词表）时引擎不认识任何注释标点，渲染**子树**（参数默认值 / 参数覆盖 /
宽度 / 连接信号）时行注释会把**同行后续元素吃进注释文本** ⇒ 精化产物文本静默丢 token：
实测裸接线 `param_default` = `'4 // note + 2'`（`+ 2` 被吞），接线后 = `'4 + 2 // note'`。

本文件守"接线没被误删"：去掉 `analyzer/shared_components.py` 的 `line_comment_starts=…`
后三条用例全红（文本面 + 直接契约面）。引擎侧词表语义契约（声明驱动 / 缺省不认识任何
标点）另见 `tests/engine/renderer/test_comment_ends_line.py`；主管线同形接线见
`pipeline/__init__.py`。
"""

import pytest

from analyzer.checker import ProjectChecker
from core._protocol import CTX_ELABORATION

pytestmark = pytest.mark.usefixtures("config_loaded")

# 值表达式**内部**带行注释：注释之后同行仍有 `+ 2` / `* 4` —— 缺接线时被并入注释文本
_DEFAULT_SRC = (
    "module lib #(parameter W = 4 // note\n"
    "                    + 2) (input clk);\n"
    "  wire [W-1:0] w;\n"
    "endmodule\n"
)
_OVERRIDE_SRC = (
    "module b;\n"
    "  parameter W = 2;\n"
    "  reg [1:0] y;\n"
    "  wire [W-1:0] x;\n"
    "  assign y = x;\n"
    "endmodule\n"
    "\n"
    "module top2;\n"
    "  b #(.W(4 // c\n"
    "         * 4)) u_b();\n"
    "endmodule\n"
)

# trivia 前缀（空白/换行/注释）：判据只看显著 token——重排许动空白，不许丢 token
_TRIVIA_PREFIXES = ("space", "newline", "comment")


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _value_tokens(checker: ProjectChecker, text: str) -> list[str]:
    """产物值文本重新词法化后的显著 token 内容序列（复刻调用方的读法）。"""
    lexer = checker._ensure_shared()["lexer"]
    return [
        t.content
        for t in lexer.tokenize(text)
        if not t.type.startswith(_TRIVIA_PREFIXES)
    ]


def _override_entry(checker: ProjectChecker, inst_name: str) -> dict:
    """`param_override` 产物里指定实例的记录（产物键 = 入口文件的绝对路径）。"""
    raw = checker._elab_extra[CTX_ELABORATION]["param_override"]
    for entries in raw.values():
        for entry in entries:
            if entry.get("inst_name") == inst_name:
                return entry
    raise AssertionError(f"param_override 缺实例 {inst_name!r}（产物：{raw!r}）")


def test_shared_renderer_keeps_line_comment_wiring(checker):
    """共享渲染器必须接语言包声明的词表：`//` 属"到行边界终止"型、普通标识符不属。"""
    renderer = checker._ensure_shared()["renderer"]
    assert renderer.comment_ends_line("// tail") is True
    assert renderer.comment_ends_line("  // 前导空白") is True
    assert renderer.comment_ends_line("W") is False


def test_param_default_value_text_keeps_tokens(checker, tmp_path):
    """参数默认值的值文本不得让行注释吃掉后续 token（缺接线 → `'4 // note + 2'`）。"""
    path = tmp_path / "lib.sv"
    path.write_text(_DEFAULT_SRC, encoding="utf-8")
    checker.check(str(path))

    value = checker._elab_extra[CTX_ELABORATION]["param_default"]["lib"]["W"]
    assert _value_tokens(checker, value) == ["4", "+", "2"], (
        f"值文本丢 token（行注释吞掉同行后续元素）：{value!r}"
    )
    assert "// note" in value, f"注释本身不应被丢弃：{value!r}"


def test_param_override_value_text_keeps_tokens(checker, tmp_path):
    """实例参数覆盖的值文本同样不得丢 token（缺接线 → `'4 // c * 4'`）。"""
    path = tmp_path / "top2.sv"
    path.write_text(_OVERRIDE_SRC, encoding="utf-8")
    checker.check(str(path))

    value = _override_entry(checker, "u_b")["params"]["W"]
    assert _value_tokens(checker, value) == ["4", "*", "4"], (
        f"覆盖值丢 token（行注释吞掉同行后续元素）：{value!r}"
    )
    assert "// c" in value, f"注释本身不应被丢弃：{value!r}"
