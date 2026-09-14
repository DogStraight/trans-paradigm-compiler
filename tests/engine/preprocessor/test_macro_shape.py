"""宏体形态分类（0.1.2 阶段 1）：包装解析四包裹 + 续接首 token 预过滤。

判定真值来自实现实测（见各 case 注释）；核心是"完整单元 vs 残缺片段"二分，
类别细分以探测顺序（stmt > decl > expr）为准——stmt 模板可容纳块内声明与
过程连续赋值，故这类宏体归"完整语句"。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor.macro_shape import (
    KIND_DECL,
    KIND_EXPR,
    KIND_PARTIAL,
    KIND_STMT,
    build_parse_probe,
    classify_macro_body,
    get_shape_config,
)

pytestmark = pytest.mark.smoke

_PROBE = build_parse_probe(DEFAULT_RULES_DIR)

# (宏体, 期望判定, 说明)
CASES: list[tuple[str, str, str]] = [
    # ── 残缺片段：首 token 续接预过滤（依赖前置上下文） ──
    ("= 1'b1", KIND_PARTIAL, "ice40 端口默认值宏（续接 =）"),
    ("[3:0]", KIND_PARTIAL, "范围片段（续接 [）"),
    ("+ 4", KIND_PARTIAL, "运算符续段（续接 +）"),
    (", .q(q)", KIND_PARTIAL, "端口连接续段（续接 ,）"),
    # ── 残缺片段：全部包裹失败 ──
    ("begin", KIND_PARTIAL, "块开头缺 end"),
    ("end", KIND_PARTIAL, "块结尾缺 begin"),
    ("else y = 2;", KIND_PARTIAL, "else 分支缺 if 头"),
    ("3:0]", KIND_PARTIAL, "半个范围（缺 [）"),
    # ── 完整单元 ──
    ("initial Q = 0;", KIND_STMT, "SB_DFF_INIT 语句体宏"),
    ("y = 1'b1;", KIND_STMT, "完整过程赋值"),
    ("if (x) y = 1; else y = 2;", KIND_STMT, "完整 if 语句"),
    ("reg [3:0] q;", KIND_STMT, "完整声明（stmt 模板容纳块内声明）"),
    ("assign y = 1'b1;", KIND_STMT, "连续赋值（过程连续赋值合法）"),
    ("1'b1", KIND_EXPR, "完整表达式"),
    ("empty_statement", KIND_EXPR, "picorv32 assert 宏体（标识符表达式）"),
    ("{a,b}", KIND_EXPR, "拼接表达式（花括号不干扰模板替换）"),
]


@pytest.mark.parametrize("body,expect,note", CASES)
def test_classify(body: str, expect: str, note: str) -> None:
    kind, basis = classify_macro_body(body, _PROBE)
    assert kind == expect, f"{body!r} → {kind}（{basis}），期望 {expect}（{note}）"


def test_config_loaded_from_language_pack() -> None:
    """包装模板与续接首 token 集来自语言包 TOML（语言知识不进代码）。"""
    wrappers, leads = get_shape_config()
    assert set(wrappers) == {"stmt", "decl", "expr", "port"}
    assert all("{b}" in (w.get("tpl") or "") for w in wrappers.values())
    assert all(w.get("pick") for w in wrappers.values()), "wrapper 缺提取路径 pick"
    assert leads, "continue_leads 未从语言包加载"


def test_classification_is_config_driven() -> None:
    """判定完全由注入配置驱动：空配置 → 无模板 → 全残缺。"""
    kind, _ = classify_macro_body("y = 1'b1;", _PROBE, cfg={})
    assert kind == KIND_PARTIAL

    custom = {
        "continue_leads": [],
        "wrappers": {"decl": {"tpl": "module m;\n{b}\nendmodule"}},
    }
    kind2, basis2 = classify_macro_body("wire a;", _PROBE, cfg=custom)
    assert kind2 == KIND_DECL, basis2


def test_partial_kind_unused_constant_guard() -> None:
    """四值常量互异（防拼写漂移）。"""
    kinds = {KIND_STMT, KIND_DECL, KIND_EXPR, KIND_PARTIAL}
    assert len(kinds) == 4
