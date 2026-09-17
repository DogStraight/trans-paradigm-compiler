"""宏体形态声明（语言包 `[macro_shape]`）：赋值后缀前导集 + 锚形态随声明走。

历史「包装解析形态分类器（wrappers 包裹模板 + continue_leads 预过滤）」的
用例已随实现一起删除——产物无读取者（判据与实测见 `preprocessor/macro_shape.py`
的删除注记）。本文件只剩仍被消费的 `suffix_leads` 声明面：它是语言知识
（哪些前导符号属于赋值后缀形态）在声明、引擎不硬编码 `=`。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor._expand import expand_tokens, scan_directives
from preprocessor.macro_shape import get_suffix_leads

pytestmark = pytest.mark.smoke


def test_suffix_leads_declared_from_language_pack() -> None:
    """verilog 声明 `=`（ice40 端口默认值宏形态）。"""
    assert get_suffix_leads() == ("=",)


def test_suffix_leads_empty_when_undeclared() -> None:
    """未声明 → 该处置不启用（该语言无赋值后缀宏形态）。"""
    assert get_suffix_leads({}) == ()
    assert get_suffix_leads({"suffix_leads": []}) == ()


def test_suffix_lead_drives_anchor_mode(config_loaded) -> None:
    """锚形态跟着声明走：在声明集内（`=` 开头）→ 行内锚 + body；不在（`+` 开头）
    → 常规 token 锚。

    锁定"声明 → 行为"这条链，防引擎回退成硬编码前缀判定。
    """
    del config_loaded  # fixture 依赖声明（语言包配置加载）
    src = "module m;\n  input a `D;\n  input b `P;\nendmodule\n"
    _table, funcs, _conds, _ph, _dl, clean, _map = scan_directives(
        src, DEFAULT_RULES_DIR
    )
    _expanded, anchors, _regions, _line_map = expand_tokens(
        clean,
        {"D": "= 1'b1", "P": "+ 1'b1"},
        rules_dir=DEFAULT_RULES_DIR,
        func_macros=funcs,
    )
    by_src = {a["source_text"]: a for a in anchors}
    assert by_src["`D"]["mode"] == "inline"
    assert by_src["`D"]["body"] == "= 1'b1"
    assert by_src["`P"]["mode"] == "token", "`+` 不在 suffix_leads → 不走行内锚处置"
