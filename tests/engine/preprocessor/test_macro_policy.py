"""宏处置策略（插件能力）：契约 / 默认方案 / 各处置执行 / 语言作用域。

引擎只做文本操作（替换 / 锚 / 区间记账）；"此处该怎么处置"是语言知识，由语言包
`[capabilities] macro_policy` 声明（契约见 `preprocessor/README.md`）。本文件锁定：

- 未声明能力 → 默认 `splice`（纯文本替换 + 宏区间）；
- verilog 策略插件的判定表（空体行首 → line / 空体行内 → inline / 非空体 → splice）；
- 方案非法 → fail-fast（mode 非法 / 非表 / line 多调用同行）；
- 语言作用域：c4 拿不到 verilog 的策略。
"""
import os

import pytest

from core.define import DEFAULT_RULES_DIR
from core.errors import ConfigError
from core.plugin_loader import load_all_components
from preprocessor._expand import expand_tokens, scan_directives
from preprocessor.macro_policy import (
    DEFAULT_PLAN,
    MODE_LINE,
    load_macro_policy,
    plan_macro,
)

pytestmark = pytest.mark.smoke

_RULES = DEFAULT_RULES_DIR


@pytest.fixture(autouse=True)
def _components_loaded():
    """每个用例前加载 verilog 组件。

    能力查找依赖已加载组件表，而测试级全局状态还原会在用例间清掉装载表
    （session 基线快照不含组件），故按用例加载（同 `test_capabilities`）。
    """
    load_all_components(os.path.join(_RULES, "plugins"))


def _expand(src: str):
    table, funcs, _c, _h, _d, clean, _m = scan_directives(src, _RULES)
    return expand_tokens(clean, table, rules_dir=_RULES, func_macros=funcs)


# ── 契约：能力查找与默认方案 ────────────────────────────────────────


def test_capability_declared_for_verilog_only(config_loaded) -> None:
    """verilog 声明了策略能力；c4 未声明（按 rules_dir 作用域查找，不串用）。"""
    del config_loaded
    assert callable(load_macro_policy(_RULES))
    assert load_macro_policy(os.path.join("grammar", "c4")) is None


def test_undeclared_capability_defaults_to_splice() -> None:
    """未声明策略 → 默认 splice（纯文本替换 + 宏区间）。"""
    assert plan_macro(None, {"name": "X", "body": "1'b1"}) == DEFAULT_PLAN


@pytest.mark.parametrize(
    "plan",
    [
        "splice",        # 非表
        {"mode": "nope"},  # mode 非法
        {},              # 缺 mode
        {"mode": "token"},  # 已删的旧模式
    ],
)
def test_illegal_plan_fails_fast(plan: object) -> None:
    """策略返回非法方案 → ConfigError（不静默降级）。"""
    with pytest.raises(ConfigError):
        plan_macro(lambda _site: plan, {"name": "X", "body": ""})  # type: ignore[arg-type]


def test_anchor_line_requires_single_call_in_line(config_loaded, monkeypatch) -> None:
    """`line` 会吞掉整行：同行多调用时 fail-fast（防静默丢内容）。"""
    del config_loaded
    import preprocessor._expand as ex

    monkeypatch.setattr(ex, "plan_macro", lambda _fn, _site: {"mode": MODE_LINE})
    src = "`define A 1'b0\n`define B 1'b1\nmodule m;\n  `A `B\nendmodule\n"
    with pytest.raises(ConfigError, match="line"):
        _expand(src)


# ── verilog 策略的判定表落到展开结果 ────────────────────────────────


def test_empty_body_macro_at_line_head_uses_line_anchor(config_loaded) -> None:
    """行首空体宏（声明修饰符）→ 整行占位（source_text = 整行原文）。"""
    del config_loaded
    src = "`define KEEP\nmodule m;\n  `KEEP reg [3:0] q;\nendmodule\n"
    _text, anchors, regions, _lm = _expand(src)
    assert [(a["mode"], a["source_text"]) for a in anchors] == [
        ("line", "  `KEEP reg [3:0] q;")
    ]
    assert regions == [], "整行占位不记宏区间"


def test_empty_body_macro_inline_uses_inline_anchor(config_loaded) -> None:
    """行内空体宏 → 行内注释锚（替换为空会丢调用原文）。"""
    del config_loaded
    src = "`define DELAY\nmodule m;\n  initial q <= `DELAY 1'b1;\nendmodule\n"
    _text, anchors, _regions, _lm = _expand(src)
    assert [a["mode"] for a in anchors] == ["inline"]


def test_nonempty_body_splices_and_records_region(config_loaded) -> None:
    """非空体宏：宏体铺进流 + 记宏区间（不建还原锚）。"""
    del config_loaded
    src = "`define STMT initial q = 0;\nmodule m;\n  `STMT\nendmodule\n"
    text, anchors, regions, _lm = _expand(src)
    assert anchors == []
    assert [r["name"] for r in regions] == ["STMT"]
    assert "initial q = 0;" in text, "宏体铺进流"
    assert "`STMT" not in text, "展开不留调用原文（还原走区间 raw 拼接）"
