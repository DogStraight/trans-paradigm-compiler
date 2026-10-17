"""C 宏 A1：**端到端**用例（生产同路：`scan_directives` → `expand_tokens`）。

来源 = 独立对抗审计的 14 条反例 + 1 条真实语料（多行块注释）。
**口径**：写死 GCC 16.1.0 的期望输出；比较用 token 序列（token 间空白不计，
字面量/注释整体算一个 token）——不直接调 `macro_expand` 私有函数。

分三类：
- `GREEN`：期望 = GCC 输出（应在 P1-1/P1-3 落地后全绿）；
- `BOUNDARY`：**已声明边界**（token 级重扫 / 跨行调用未实现）⇒ 断言**当前输出**
  （守卫式，不用 xfail——边界落地时必须显式改这里）；
- `MULTILINE_COMMENT`：真实语料里块注释续行内的宏名不得展开（P1-3）。
"""
import re

import pytest

from lexer.comment_syntax import load_comment_syntax
from preprocessor import scan_directives
from preprocessor._expand import expand_tokens
from preprocessor.macro_expand import mask_spans, tokenize
from preprocessor.macro_shape import load_macro_operators

pytestmark = pytest.mark.smoke

PACK = "grammar/c"
_OPS = load_macro_operators(rules_dir=PACK)
_SYNTAX = load_comment_syntax(PACK)
# 指令行占位 marker（`// <tpc:directive:N>`）不参与比较
_MARKS = re.compile(r"\s*//\s*<tpc:directive:\d+>\s*")


def _strip(text: str) -> str:
    kept = [ln for ln in text.splitlines() if ln.strip() and not _MARKS.fullmatch(ln)]
    return " | ".join(kept)


def _norm(text: str) -> str:
    """比较口径：token 序列（同审计脚本，用公开的 `mask_spans`/`tokenize`）。"""
    spans = mask_spans(text, _OPS.string_delimiters, _OPS.escape, _SYNTAX)
    return "|".join(t.text for t in tokenize(text, _OPS, spans) if t.text.strip())


def _engine(src: str) -> str:
    """生产同路：扫指令 → 展开（**不**走审计脚本的私有捷径）。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, PACK)
    out, *_tail = expand_tokens(
        clean, macro_defs, rules_dir=PACK, func_macros=func_macros
    )
    return _strip(out)


# (id, 说明, 源码, GCC 期望输出)
GREEN: list[tuple[str, str, str, str]] = [
    ("P0-1", "`##` 两侧空格", "#define CONCAT(a,b) a ## b\nint r = CONCAT(x,y);\n",
     "int r = xy;"),
    ("P0-2", "`#` 与形参间空格", "#define STR(s) # s\nconst char *p = STR(hi);\n",
     'const char *p = "hi";'),
    ("P0-3", "实参字符串内逗号", '#define F(a,b) a+b\nint r = F("x,y",3);\n',
     'int r = "x,y"+3;'),
    ("P0-4", "实参字符串内 `)`", '#define F(a,b) a+b\nint r = F(")",1);\n',
     'int r = ")"+1;'),
    ("P0-5", "短名吃长名前缀", "#define A 1\n#define AB 2\nint r = AB;\n",
     "int r = 2;"),
    ("P0-6", "函数宏名后有空格", "#define F(x) x+1\nint r = F (2);\n",
     "int r = 2+1;"),
    ("P0-7", "函数宏名裸出现不替换", "#define F(x) x+1\nint r = F;\n",
     "int r = F;"),
    ("P1-2", "`#undef` 清形参表",
     "#define F(x) x+1\n#undef F\n#define F 2\nint r = F(3);\n", "int r = 2(3);"),
    ("P2-1", "自身再出现不预展开两次", "#define x x x\nint r = x;\n",
     "int r = x x;"),
    ("P2-2", "字符串化内注释→空格",
     "#define S(a) #a\nconst char *p = S(a /* c */ b);\n",
     'const char *p = "a b";'),
]

#: P1-1：`#__VA_ARGS__` 用**实参原文切片**（GCC 16.1.0 实测四例）
P11: list[tuple[str, str, str, str]] = [
    ("P1-1a", "无间隔", "#define V(...) #__VA_ARGS__\nconst char *p = V(a,b);\n",
     'const char *p = "a,b";'),
    ("P1-1b", "逗号后双空格",
     "#define V(...) #__VA_ARGS__\nconst char *p = V(a ,  b);\n",
     'const char *p = "a , b";'),
    ("P1-1c", "两侧空白",
     "#define V(...) #__VA_ARGS__\nconst char *p = V( a, b );\n",
     'const char *p = "a, b";'),
    ("P1-1d", "空变参",
     "#define V(...) #__VA_ARGS__\nconst char *p = V();\n",
     'const char *p = "";'),
]

#: **已声明边界**：断言当前输出（token 级重扫 / 跨行调用落地时必须重新审视）
BOUNDARY: list[tuple[str, str, str, str]] = [
    ("P0-8", "边界①：替换结果里再现的调用不重扫（别名调用）",
     "#define f(x) x+1\n#define g f\nint r = g(2);\n", "int r = f(2);"),
    ("P0-9", "边界②：实参跨行的调用不展开",
     "#define F(a,b) a+b\nint r = F(1,\n            2);\n",
     "int r = F(1, | 2);"),
    ("P0-10", "边界①：替换结果里的函数宏调用不重扫",
     "#define f(a) a*g\n#define g(a) f(a)\nint r = f(2)(9);\n",
     "int r = 2*g(9);"),
]


@pytest.mark.parametrize("cid,desc,src,expected", GREEN, ids=[c[0] for c in GREEN])
def test_end_to_end_green(cid: str, desc: str, src: str, expected: str) -> None:
    """端到端（生产同路）：期望 = GCC 16.1.0 输出。"""
    del cid
    actual = _engine(src)
    assert _norm(actual) == _norm(expected), f"{desc}\n实际: {actual}"


@pytest.mark.parametrize("cid,desc,src,expected", P11, ids=[c[0] for c in P11])
def test_end_to_end_hash_varargs(cid: str, desc: str, src: str, expected: str) -> None:
    """`#__VA_ARGS__` 精确拼写（P1-1，原文切片）。"""
    del cid
    actual = _engine(src)
    assert _norm(actual) == _norm(expected), f"{desc}\n实际: {actual}"


@pytest.mark.parametrize(
    "cid,desc,src,expected", BOUNDARY, ids=[c[0] for c in BOUNDARY]
)
def test_declared_boundary_guard(cid: str, desc: str, src: str, expected: str) -> None:
    """**已声明边界**：断言当前输出（守卫式，不用 xfail）。

    边界落地（token 级重扫 / 跨行调用）时**必须显式改这里**——不要让"当前输出"
    静默漂移。边界说明见 `preprocessor/README.md`「已知边界」。
    """
    del cid
    actual = _engine(src)
    assert _norm(actual) == _norm(expected), (
        f"{desc}\n实际: {actual}\n（若这是修复后的新行为，请同步更新本守卫断言）"
    )


def test_multiline_block_comment_inner_name_not_expanded() -> None:
    """真实语料多行块注释：**续行内**的宏名不得被当调用展开（P1-3）。"""
    sample = open(
        "tests/languages/c/samples/edge_comments.c", encoding="utf8"
    ).read()
    src = "#define flat 1\n" + sample
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, PACK)
    out, *_tail = expand_tokens(
        clean, macro_defs, rules_dir=PACK, func_macros=func_macros
    )
    after = next(
        (ln for ln in out.splitlines() if "flat" in ln or "列表 1" in ln), ""
    )
    assert after, "样本中应有注释续行（含 flat / 列表 1）"
    assert "flat" in after, (
        "块注释续行内的宏名被展开了（掩码未跨行生效）：" + after
    )
