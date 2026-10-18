"""接缝重扫（token 级重扫的边界①）：宏体末尾的函数宏名 + 源码后续 `(...)`。

背景（A1 已声明边界①，循环 #23 落地）：文本层逐调用替换，替换文本不参与后续
源码的重扫 ⇒ `#define g f` + `g(2)` 旧行为 `f(2)`（GCC `2+1`）；
`f(2)(9)` 旧行为 `2*g(9)`（GCC `2*9*g`）。C99 §6.10.3.4：替换列表**连同其余源码**
一起重扫描。本轮在"宏体 + 源码后续"的接缝处补齐（区域/锚/行映射复用既有机制）。

**判据口径**（独立审计后定）：
- `CRITERIA`（**改前红**）：别名调用、互递归别名、verilog 前缀接缝、hideset 交集
  判别器（C2）——动手前断言旧输出会红；
- `GUARDS`（**改前就绿**，只能当回归守卫，各行对应一种坏实现）：
  自引用不展开（坏实现 = 丢 hideset/接缝用并集）、体末非名不过度接缝（坏实现 =
  见名就接）、互递归循环不膨胀（坏实现 = 预算失效）、无括号不接（坏实现 = 过度接缝）；
- `BOUNDARY`（已声明边界，守卫当前输出）：实参跨行（A1 边界②）、名字与括号跨行、
  "使用先于定义"沿用最终宏表（既有近似，接缝面随之扩大）。
"""
import re

import pytest

from preprocessor import scan_directives
from preprocessor._expand import expand_tokens
from preprocessor.macro_expand import expand_text_tokens
from preprocessor.macro_shape import load_macro_operators

pytestmark = pytest.mark.smoke

PACK = "grammar/c"
_VPACK = "grammar/verilog"

_MARKS = re.compile(r"\s*//\s*<tpc:directive:\d+>\s*")
_OPS = load_macro_operators(rules_dir=PACK)


def _call_args(pack: str):
    from preprocessor.macro_shape import load_macro_call_args

    return load_macro_call_args(rules_dir=pack)


def _engine(src: str, pack: str = PACK) -> str:
    """生产同路：扫指令 → 展开（不直接调私有捷径）。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, pack)
    out, *_tail = expand_tokens(
        clean, macro_defs, rules_dir=pack, func_macros=func_macros
    )
    return _strip(out)


def _strip(text: str) -> str:
    kept = [ln for ln in text.splitlines() if ln.strip() and not _MARKS.fullmatch(ln)]
    return " | ".join(kept)


def _expand_facts(src: str) -> tuple[str, list[dict]]:
    """展开 + 调用点事实（引擎层；不经过 timeline 过滤）。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, PACK)
    invocations: list[dict] = []
    out, *_tail = expand_tokens(
        clean,
        macro_defs,
        rules_dir=PACK,
        func_macros=func_macros,
        out_invocations=invocations,
    )
    return _strip(out), invocations


# ── 判据（改前红）─────────────────────────────────────────────


CRITERIA: list[tuple[str, str, str, str]] = [
    (
        "R1-alias",
        "对象宏替换出函数宏名 + 源码实参（别名调用）",
        "#define f(x) x+1\n#define g f\nint r = g(2);\n",
        "int r = 2+1;",
    ),
    (
        "R2-mutual",
        "互递归别名：f(2)(9) ⇒ 2*9*g（hideset 交集口径，并集会停在 2*f(9)）",
        "#define f(a) a*g\n#define g(a) f(a)\nint r = f(2)(9);\n",
        "int r = 2*9*g;",
    ),
    (
        "R3-c2",
        "hideset 交集判别器：接缝引用体末名字时不得用并集（GCC 2*f）",
        "#define X f\n#define m X\n#define f(a) a*X\nint r = m(2);\n",
        "int r = 2*f;",
    ),
    (
        "R4-comment",
        "名字与实参括号间有注释（注释在翻译阶段已换成空白）",
        "#define f(x) x+1\n#define g f\nint r = g /*c*/ (2);\n",
        "int r = 2+1;",
    ),
]


@pytest.mark.parametrize("cid,desc,src,expected", CRITERIA, ids=[c[0] for c in CRITERIA])
def test_rescan_criteria(cid: str, desc: str, src: str, expected: str) -> None:
    """改前红判据：接缝处新形成的调用必须继续展开（GCC 16.1.0 对拍口径）。"""
    del cid
    actual = _engine(src)
    assert actual == expected, f"{desc}\n实际: {actual}"


def test_rescan_criteria_verilog_prefix() -> None:
    """改前红：verilog 前缀接缝 `` `g(2) ``（宏体是 `` `f ``）⇒ `` 2+1 ``。"""
    actual = _engine(
        "`define f(x) x+1\n`define g `f\nint r = `g(2);\n", _VPACK
    )
    assert actual == "int r = 2+1;"


# ── 回归守卫（改前就绿；各行写明"什么坏实现会让它红"）────────────


GUARDS: list[tuple[str, str, str, str]] = [
    (
        "G1-self",
        "自引用：体末 f 带 hide {f} ⇒ 接缝不得再展开（坏实现 = 丢 hideset / 接缝 hideset 不取交集）",
        "#define f(a) a*f\nint r = f(2)(9);\n",
        "int r = 2*f(9);",
    ),
    (
        "G2-no-name",
        "体末不是宏名 ⇒ 不接（坏实现 = 见括号就接）",
        "#define f(a) a+1\nint r = f(2)(9);\n",
        "int r = 2+1(9);",
    ),
    (
        "G3-recursion",
        "互递归宏名循环不膨胀（坏实现 = 预算/hideset 失效）",
        "#define A B\n#define B A\nint r = A;\n",
        "int r = A;",
    ),
    (
        "G4-no-paren",
        "后续没有实参括号 ⇒ 不接（坏实现 = 过度接缝）",
        "#define f(x) x+1\n#define g f\nint r = g + 2;\n",
        "int r = f + 2;",
    ),
]


@pytest.mark.parametrize("cid,desc,src,expected", GUARDS, ids=[c[0] for c in GUARDS])
def test_rescan_guards(cid: str, desc: str, src: str, expected: str) -> None:
    """回归守卫：不变式 + 破坏它的坏实现（不是"改前红"判据）。"""
    del cid
    actual = _engine(src)
    assert actual == expected, f"{desc}\n实际: {actual}"


def test_token_variant_keeps_hideset() -> None:
    """token 返回变体必须保留 hideset（`join()` 后再 tokenize 会丢 ⇒ 自引用守卫失效）。"""
    toks = expand_text_tokens(
        "f(2)",
        {"f": "x*f"},
        {"f": ["x"]},
        _call_args(PACK),
        operators=_OPS,
        syntax=None,
    )
    assert "".join(t.text for t in toks) == "2*f"
    assert "f" in toks[-1].hide


# ── 区域/事实（机制复用判据）────────────────────────────────


def test_junction_region_covers_consumed_source() -> None:
    """接缝消费的源码并入本调用区间：`source_text` 覆盖 `g(2)`，`body` 是展开文本。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(
        "#define f(x) x+1\n#define g f\nint r = g(2);\n", PACK
    )
    _out, _stack, regions, _lm = expand_tokens(
        clean, macro_defs, rules_dir=PACK, func_macros=func_macros
    )
    assert len(regions) == 1
    reg = regions[0]
    assert reg["name"] == "g"
    assert reg["source_text"] == "g(2)"
    assert reg["body"] == "2+1"


def test_junction_call_site_fact_recorded() -> None:
    """接缝展开出的函数宏调用也记调用点事实（MAC001 的输入面）。"""
    out, inv = _expand_facts("#define f(a, b) a+b\n#define g f\nint r = g(2);\n")
    assert out == "int r = 2+;"
    assert [(i["name"], i["slots"], tuple(i["params"])) for i in inv] == [
        ("f", 1, ("a", "b"))
    ]


# ── 已声明边界（守卫当前输出）────────────────────────────────


def test_boundary_cross_line_name_paren() -> None:
    """边界：名字与实参括号跨行（逐行展开）⇒ 不接；落地时必须改本守卫。"""
    assert _engine("#define f(x) x+1\n#define g f\nint r = g\n(2);\n") == (
        "int r = f | (2);"
    )


def test_boundary_use_before_define_final_table() -> None:
    """边界：展开器仍用**最终宏表**（既有近似）⇒ 定义前的 `g(2)` 也被接缝重扫。"""
    assert _engine(
        "int r = g(2);\n#define f(a, b) a+b\n#define g f\n"
    ) == "int r = 2+;"
