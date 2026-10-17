"""宏展开核心 `macro_expand`：hideset 重扫描语义。

锁定（对应首片 A1 的方案 B②）：
- **自引用抑制**：`#define x x` ⇒ `x` 不展开；
- **互递归**：`y→z→y` ⇒ 停在 `z`；
- **传递展开**：`c→b→a→1` ⇒ `1`；
- **调用前缀**：verilog 形态下裸同名标识符**不**展开，`` `NAME `` 才展开（前缀随调用消费）；
- **函数宏替参**：具名形参替换 + 实参先展开；
- **预算守卫**：`max_iterations` 只是资源上限（超限保留原文，不抛）。
"""
import pytest

from preprocessor.macro_expand import expand_text
from preprocessor.macro_shape import MacroCallArgs

pytestmark = pytest.mark.smoke

_CALL_ARGS = MacroCallArgs(
    open="(", close=")", separator=",", nesting=(("(", ")"),)
)


def _expand(
    text: str,
    defs: dict[str, str],
    funcs: dict[str, list[str]] | None = None,
    *,
    prefix: str = "",
    budget: int = 128,
) -> str:
    return expand_text(
        text, defs, funcs or {}, _CALL_ARGS, prefix=prefix, budget=budget
    )


def test_self_reference_not_expanded() -> None:
    """`#define x x` ⇒ `x`（hideset 抑制；旧算法靠"直接自引用预判"近似）。"""
    assert _expand("x", {"x": "x"}) == "x"


def test_hideset_prevents_expansion_growth() -> None:
    """`#define x x x` 展开 `x` ⇒ **`x x`**（判别式用例，对拍 GCC）。

    只断言 `#define x x` 时，无 hideset 的实现被**预算截断**恰好截回 `x` ⇒
    测不出抑制。换成 `x x` 后无 hideset 会膨胀到预算上限 ⇒ 文本必不同。
    """
    assert _expand("x", {"x": "x x"}) == "x x"


def test_mutual_recursion_stops_at_visited_name() -> None:
    """`y→z→y` ⇒ `z`（与 GCC 实测一致：停在被 hideset 挡住的那一刻）。"""
    assert _expand("z", {"y": "z", "z": "y"}) == "z"


def test_transitive_bodies_expand() -> None:
    """传递展开：`c→b→a→1` ⇒ `1`。"""
    assert _expand("c", {"a": "1", "b": "a", "c": "b"}) == "1"


def test_call_prefix_required_for_prefixed_language() -> None:
    """前缀语言：裸 `FOO` **不**展开；`` `FOO `` 展开且前缀被消费。"""
    defs = {"FOO": "1"}
    assert _expand("FOO", defs, prefix="`") == "FOO"
    assert _expand("`FOO", defs, prefix="`") == "1"


def test_function_macro_substitutes_params() -> None:
    """具名形参替换：`f(2)` + `f(x)=x+1` ⇒ `2+1`。"""
    assert _expand("f(2)", {"f": "x+1"}, {"f": ["x"]}) == "2+1"


def test_function_macro_chain_through_object_macros() -> None:
    """`h→g→f`，`f` 为函数宏 ⇒ `h(2)` ⇒ `2+1`（与 GCC 实测同语义）。"""
    defs = {"h": "g", "g": "f", "f": "x+1"}
    assert _expand("h(2)", defs, {"f": ["x"]}) == "2+1"


def test_arguments_are_expanded_before_substitution() -> None:
    """实参先展开：`f(g)` 且 `g→1`、`f(x)=x` ⇒ `1`。"""
    assert _expand("f(g)", {"f": "x", "g": "1"}, {"f": ["x"]}) == "1"


def test_budget_guard_keeps_text_instead_of_raising() -> None:
    """预算守卫：超限保留原文，不抛异常（资源上限不是第二套算法）。"""
    # 递归链 a1→a2→…→a9，预算 2 ⇒ 只展开两跳，剩余保留
    defs = {f"a{i}": f"a{i + 1}" for i in range(1, 10)}
    out = _expand("a1", defs, budget=2)
    assert out.startswith("a"), out
    assert out != "a10", "预算应阻止全部展开"
