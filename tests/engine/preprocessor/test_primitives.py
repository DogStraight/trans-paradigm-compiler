"""preprocessor primitives 单元测试。

直接调用各指令 handler（define/undef/ifdef/include），验证行为：
  - define：object-like / function-like 形参表
  - undef：移除宏
  - ifdef 族：条件栈、active 判定（predefined/undefine 优先级）、占位压缩
  - include：路径解析（""/<>）、递归、循环检测
"""

import os

import pytest

from core.define import FileManager
from preprocessor.primitives.registry import (
    get_primitive,
    get_primitive_kind,
    list_primitives,
)

# ── 公共 fixture ──────────────────────────────


def _ctx(**kw) -> dict:
    """构造 handler 共享上下文。"""
    ctx = {
        "macro_defs": {},
        "_func_params": {},
        "_cond_blocks": [],
        "_cond_seq": 0,
        "_cond_placeholders": {},
        "_inject_lines": [],
        "_undefine": set(),
        "_predefined": {},
        "source_dir": os.path.abspath("."),
        "inc_dirs": [],
        "_include_config": {},
        "_include_stack": set(),
        "rules_dir": FileManager.get_full_path("grammar/verilog"),
        "directive_lines": [],
    }
    ctx.update(kw)
    return ctx


def _call(name: str, stripped: str, ctx: dict, prefix: str = "`") -> None:
    """调用指定 handler。"""
    h = get_primitive(name)
    assert h is not None, f"primitive {name} 未注册"
    h(stripped, prefix, name, ctx)


class TestRegistry:
    """注册表：5 个 primitive 全部注册，control 类型正确。"""

    def test_all_primitives_registered(self):
        names = list_primitives()
        assert "define" in names
        assert "undef" in names
        assert "ifdef" in names
        assert "include" in names

    def test_control_kind(self):
        assert get_primitive_kind("ifdef") == "control"
        assert get_primitive_kind("define") == "normal"


class TestDefine:
    """`define：object-like + function-like。"""

    def test_object_like(self):
        ctx = _ctx()
        _call("define", "`define WIDTH 8", ctx)
        assert ctx["macro_defs"]["WIDTH"] == "8"

    def test_object_like_multitoken_body(self):
        ctx = _ctx()
        _call("define", "`define DEBUG debug_command", ctx)
        assert ctx["macro_defs"]["DEBUG"] == "debug_command"

    def test_function_like_params(self):
        ctx = _ctx()
        _call("define", "`define MIN(a, b) ((a) < (b) ? (a) : (b))", ctx)
        assert ctx["_func_params"]["MIN"] == ["a", "b"]
        assert "((a) < (b) ? (a) : (b))" in ctx["macro_defs"]["MIN"]

    def test_function_like_unclosed_params_fallback(self):
        """形参表未闭合 → 退化为 object-like（容错）。"""
        ctx = _ctx()
        _call("define", "`define FOO(a, b body", ctx)
        assert "FOO" in ctx["macro_defs"]
        assert "FOO" not in ctx["_func_params"]

    def test_no_name_noop(self):
        ctx = _ctx()
        _call("define", "`define ", ctx)
        assert ctx["macro_defs"] == {}


class TestUndef:
    """`undef：移除宏。"""

    def test_undef_removes(self):
        ctx = _ctx(macro_defs={"X": "1", "Y": "2"})
        _call("undef", "`undef X", ctx)
        assert "X" not in ctx["macro_defs"]
        assert "Y" in ctx["macro_defs"]

    def test_undef_missing_noop(self):
        ctx = _ctx()
        _call("undef", "`undef NOTHERE", ctx)  # 不抛异常
        assert ctx["macro_defs"] == {}


class TestIfdef:
    """`ifdef 族：条件栈 + active 判定 + 占位压缩。"""

    def test_ifdef_defined_active(self):
        ctx = _ctx(macro_defs={"F": "1"})
        _call("ifdef", "`ifdef F", ctx)
        assert len(ctx["_cond_blocks"]) == 1
        assert ctx["_cond_blocks"][0]["branches"][0]["active"] is True

    def test_ifdef_undefined_inactive(self):
        ctx = _ctx(macro_defs={})
        _call("ifdef", "`ifdef F", ctx)
        assert ctx["_cond_blocks"][0]["branches"][0]["active"] is False

    def test_ifndef_negated(self):
        ctx = _ctx(macro_defs={})
        _call("ifndef", "`ifndef F", ctx)  # ifndef 是独立 primitive
        assert ctx["_cond_blocks"][0]["branches"][0]["active"] is True
        assert ctx["_cond_blocks"][0]["negated"] is True

    def test_predefined_overrides_source(self):
        """外部 -D 定义优先于源码（即使源码未定义）。"""
        ctx = _ctx(macro_defs={}, _predefined={"F": "1"})
        _call("ifdef", "`ifdef F", ctx)
        assert ctx["_cond_blocks"][0]["branches"][0]["active"] is True

    def test_undefine_overrides_predefined(self):
        """外部 -U 优先于 -D 与源码。"""
        ctx = _ctx(macro_defs={"F": "1"}, _predefined={"F": "1"}, _undefine={"F"})
        _call("ifdef", "`ifdef F", ctx)
        assert ctx["_cond_blocks"][0]["branches"][0]["active"] is False

    def test_else_switches_active(self):
        ctx = _ctx(macro_defs={})
        _call("ifdef", "`ifdef F", ctx)
        _call("else", "`else", ctx)
        block = ctx["_cond_blocks"][0]
        # else 分支 active（原 ifdef 分支 inactive）
        assert block["branches"][1]["active"] is True
        assert block["branches"][0]["active"] is False

    def test_endif_flushes_placeholder(self):
        """endif 后非管线内容压缩成占位。"""
        ctx = _ctx(macro_defs={})
        _call("ifdef", "`ifdef F", ctx)
        # 给 active 分支加内容
        block = ctx["_cond_blocks"][0]
        block["branches"][0]["lines"].append("    code = 1;")
        _call("endif", "`endif", ctx)
        # 占位生成（inactive ifdef 行 + 内容压缩成占位）
        assert ctx["_cond_placeholders"], "应生成条件占位"


class TestInclude:
    """`include：路径解析 + 递归 + 循环检测。"""

    def test_include_quote_relative(self, tmp_path):
        (tmp_path / "inc.v").write_text("wire x;", encoding="utf-8")
        ctx = _ctx(source_dir=str(tmp_path), inc_dirs=[str(tmp_path)])
        _call("include", '`include "inc.v"', ctx)
        # 文件读入 → macro_defs/directive_lines 或 _inject_lines 至少一项变化
        assert ctx["macro_defs"] or ctx["directive_lines"] or ctx["_inject_lines"], (
            "include 应读取文件内容"
        )

    def test_include_angle_search_dirs(self, tmp_path):
        (tmp_path / "sys.v").write_text("wire y;", encoding="utf-8")
        ctx = _ctx(source_dir=str(tmp_path), inc_dirs=[str(tmp_path)])
        _call("include", "`include <sys.v>", ctx)
        assert ctx["macro_defs"] or ctx["directive_lines"] or ctx["_inject_lines"]

    def test_include_missing_silent(self, tmp_path):
        """找不到文件 + silent → 不打印不报错。"""
        ctx = _ctx(source_dir=str(tmp_path), inc_dirs=[], _include_config={"silent": True})
        _call("include", '`include "nope.v"', ctx)  # 不抛异常
        assert ctx["macro_defs"] == {}
