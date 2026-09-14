"""宏体子树提取（0.1.2 阶段 4b-1）：按包裹配置（pick/skip_*）钻取宏体节点。

引擎用语言包 `[macro_shape.wrappers.<key>]` 的 `pick`（节点名路径）钻取容器，
取 children 去掉 `skip_head`/`skip_tail` → 合成 `MacroBody` 包装节点。
提取路径是语言语法知识（进配置），引擎只做通用钻取。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor.macro_shape import build_parse_ast, extract_macro_body

pytestmark = pytest.mark.smoke

_PARSE_AST = build_parse_ast(DEFAULT_RULES_DIR)

# (包裹形态, 宏体, 期望的首个子节点名)
CASES = [
    ("stmt", "x = 1'b1;", "BlockingAssign"),
    ("decl", "wire a;", "WireDecl"),
    ("expr", "1'b1", "Number"),
    ("port", "= 1'b1", "Number"),
]


@pytest.mark.parametrize("shape,body,expect", CASES)
def test_extract_single_unit(shape: str, body: str, expect: str) -> None:
    wrap = extract_macro_body(body, shape, _PARSE_AST)
    assert wrap is not None, (shape, body)
    assert wrap.node_name == "MacroBody"
    kids = list(wrap.iter_children())
    assert len(kids) == 1, [k.node_name for k in kids]
    assert kids[0].node_name == expect


def test_extract_multi_stmt_body() -> None:
    """语句包裹下多语句宏体 → 多个顶层单元。"""
    wrap = extract_macro_body("x = 1'b1;\ny = 1'b0;", "stmt", _PARSE_AST)
    assert wrap is not None
    assert len(list(wrap.iter_children())) == 2


def test_extract_multi_decl_body() -> None:
    """声明包裹下多声明宏体（skip_tail 去掉 module 名后全部保留）。"""
    wrap = extract_macro_body("wire a;\nwire b;", "decl", _PARSE_AST)
    assert wrap is not None
    assert [k.node_name for k in wrap.iter_children()] == ["WireDecl", "WireDecl"]


def test_extract_partial_returns_none() -> None:
    """残缺片段无法成完整单元 → 提取返回 None（调用方回退文本级处理）。

    注：`begin`/`end` 单看会在 stmt 包裹下被当作合法嵌套块（形态分类同样判完整），
    故用确定残缺的样本（续接符号 / 半个范围）。
    """
    assert extract_macro_body("= 1'b1", "stmt", _PARSE_AST) is None
    assert extract_macro_body("3:0]", "stmt", _PARSE_AST) is None
