"""tests/engine/renderer/test_doc_tri_state.py — 换行三态的 Doc 层语义。

三态（见 renderer/doc.py，配置词汇见 renderer/primitives/{line,soft_break}.py）：

  | 状态        | Doc          | flat            | broken     | 配置键            |
  |-------------|--------------|-----------------|------------|-------------------|
  | 软换行      | `Line`       | 空格            | 换行       | `{ soft = true }` |
  | 条件换行    | `LineBreak`  | 消失            | 换行       | `{ break = true }` |
  | 强制换行    | `HardBreak`  | 换行（且向上强制所在组断开） | 换行 | `{ hard_break = true }` |

本测试固化：三态在宽/窄布局下的行为、`HardBreak` 的**向上传播**（含它的
`group()` 不再生成 Union → 外层同样强制断开）、以及"HardBreak 之后紧邻的
条件断不再产生新行"的幂等挤除（否则叠加出空行）。
"""

from renderer.doc import (
    Align,
    Concat,
    Empty,
    HardBreak,
    Line,
    LineBreak,
    Nest,
    Prefix,
    Text,
    group,
    layout,
)
from renderer.doc import _drop_break_after_hardbreak, _strip_leading_hardbreak

_WIDE = 1000
_NARROW = 1


def _render(doc, width: int = _WIDE) -> str:
    return layout(doc, width)


# ── 三态基本行为 ──

def test_soft_break_is_space_when_flat_newline_when_broken() -> None:
    doc = group(Concat([Text("x"), Line(), Text("y")]))
    assert _render(doc) == "x y"
    assert _render(doc, _NARROW) == "x\ny"


def test_conditional_break_disappears_when_flat() -> None:
    doc = group(Concat([Text("x"), LineBreak(), Text("y")]))
    assert _render(doc) == "xy"          # flat：不产生空格，也不换行
    assert _render(doc, _NARROW) == "x\ny"


def test_hard_break_breaks_even_when_wide() -> None:
    doc = group(Concat([Text("x"), Line(), Text("y"), HardBreak(), Text("z")]))
    assert _render(doc) == "x\ny\nz"     # 宽度充足也断，且同组软断随之断开


# ── 向上传播（含 HardBreak 的组必断） ──

def test_hard_break_forces_enclosing_group_broken() -> None:
    """含 HardBreak 的 group 不生成 Union → 同组软断全部断开。"""
    inner = group(Concat([Text("b"), HardBreak(), Text("c")]))
    outer = group(Concat([Text("a"), Line(), inner]))
    assert _render(outer) == "a\nb\nc"


def test_soft_only_group_still_flattens() -> None:
    """对照组：不含 HardBreak 的组照旧可扁平（改动不波及普通组）。"""
    inner = group(Concat([Text("b"), Line(), Text("c")]))
    outer = group(Concat([Text("a"), Line(), inner]))
    assert _render(outer) == "a b c"


def test_nested_group_authority_not_overridden() -> None:
    """嵌套 Union（子组）自行决定断开与否——挤除/传播都不越过嵌套组。"""
    inner = group(Concat([Text("b"), Line(), Text("c")]))   # 可扁平
    outer = Concat([Text("a"), Line(), inner, HardBreak(), Text("z")])
    assert _render(outer) == "a\nb c\nz"


# ── HardBreak 之后的条件断幂等挤除 ──

def test_conditional_break_after_hardbreak_is_dropped() -> None:
    """HardBreak 已结束该行 → 紧跟的条件断不再产生新行（否则多空行）。"""
    doc = Concat([Text("x"), HardBreak(), LineBreak(), Text("y")])
    out = _drop_break_after_hardbreak(doc)
    assert isinstance(out, Concat)
    assert not any(isinstance(d, LineBreak) for d in out.docs)  # 条件断被挤掉
    assert _render(out) == "x\ny"


def test_soft_break_after_hardbreak_not_dropped() -> None:
    """软断不挤：它同时承担“下一项另起一行”的语义（结构性断言）。

    组外软断本就换行（本引擎语义：只有组内 flat 才折成空格），故这里断言
    它仍在 doc 里、且渲染形态不变。
    """
    doc = Concat([Text("x"), HardBreak(), Line(), Text("y")])
    out = _drop_break_after_hardbreak(doc)
    assert isinstance(out, Concat)
    assert any(isinstance(d, Line) for d in out.docs)
    assert _render(out) == "x\n\ny"


def test_consecutive_breaks_kept_for_blank_lines() -> None:
    """连续 Break 是显式空行（`tail_break = 2`）——不得被挤除。"""
    doc = Concat([Text("endmodule"), HardBreak(), HardBreak(), Text("next")])
    assert _render(_drop_break_after_hardbreak(doc)) == "endmodule\n\nnext"


# ── 行状态去冗余：_strip_leading_hardbreak ──
#
# layout 的 Concat 分支在“当前行只余缩进且由非硬断行结束”时会调它，去掉子项
# 开头的 HardBreak（否则“父断行 + 注释首断行”叠出纯空白行）。这里固化它沿
# Concat/Nest/Align/Prefix 下钻的行为与全空折叠。


def test_strip_leading_hardbreak_plain_and_concat() -> None:
    assert isinstance(_strip_leading_hardbreak(HardBreak()), Empty)
    stripped = _strip_leading_hardbreak(Concat([HardBreak(), Text("x")]))
    assert isinstance(stripped, Concat) and _render(stripped) == "x"
    only = _strip_leading_hardbreak(Concat([HardBreak()]))
    assert isinstance(only, Empty)


def test_strip_leading_hardbreak_descends_wrappers() -> None:
    """Nest/Align/Prefix 包装下的首叶硬换行同样被去掉（包装保留）。"""
    nested = _strip_leading_hardbreak(Nest(4, Concat([HardBreak(), Text("x")])))
    assert isinstance(nested, Nest) and _render(nested) == "x"
    aligned = _strip_leading_hardbreak(Align(8, Concat([HardBreak(), Text("x")])))
    assert isinstance(aligned, Align) and _render(aligned) == "x"
    prefixed = _strip_leading_hardbreak(Prefix(2, Concat([HardBreak(), Text("x")])))
    assert isinstance(prefixed, Prefix) and _render(prefixed) == "  x"


def test_strip_leading_hardbreak_collapses_empty_wrapper() -> None:
    """包装内只剩硬换行 → 整体折叠为 Empty（不留空包装）。"""
    assert isinstance(_strip_leading_hardbreak(Nest(4, HardBreak())), Empty)
    assert isinstance(_strip_leading_hardbreak(Align(8, HardBreak())), Empty)
    assert isinstance(_strip_leading_hardbreak(Prefix(2, HardBreak())), Empty)


def test_strip_leading_hardbreak_keeps_non_leading_break() -> None:
    """非首叶的硬换行不动（如 `x` 之后的硬换行）。"""
    doc = Concat([Text("x"), HardBreak(), Text("y")])
    assert _render(_strip_leading_hardbreak(doc)) == "x\ny"
