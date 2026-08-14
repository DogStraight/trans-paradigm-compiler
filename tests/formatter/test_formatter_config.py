"""formatter 品类配置——配置驱动回归测试。

品类定义外部化到语言包 tpc.toml（[[formatter.categories]]），
build_engine 从 ConfigRegistry 读取，fallback 到代码内 DEFAULT_CATEGORIES。
"""

import pytest

pytestmark = pytest.mark.usefixtures("config_loaded")


def test_categories_loaded_from_config():
    """tpc.toml 的 [[formatter.categories]] 被 ConfigRegistry 注册。"""
    from core.config_registry import ConfigRegistry
    cats = ConfigRegistry.get("formatter.categories")
    assert isinstance(cats, list) and cats
    names = {c.get("name") for c in cats}
    expected = {
        "port_dir", "declaration", "parameter", "assignment",
        "genvar_integer", "function", "task",
    }
    assert expected <= names, f"配置品类缺失: {expected - names}"


def test_categories_have_matchers():
    """每个品类都有 matcher（first_token 驱动匹配）。"""
    from core.config_registry import ConfigRegistry
    cats = ConfigRegistry.get("formatter.categories")
    for c in cats:
        matcher = c.get("matcher", {})
        assert matcher.get("first_token"), f"品类 {c.get('name')} 缺 first_token matcher"


def test_build_engine_uses_config():
    """build_engine 从配置构建：indent → 品类 → inst_port。"""
    from grammar.verilog.plugins.formatter import build_engine
    eng = build_engine()
    names = [p.name for p in eng._passes]
    assert names[0] == "indent"
    assert "port_dir" in names
    assert "declaration" in names
    assert "inst_port" in names
    assert names[-1] == "inst_port"


def test_explicit_categories_override():
    """显式传入 categories 优先于配置。"""
    from grammar.verilog.plugins.formatter import build_engine
    eng = build_engine(categories=[{"name": "custom", "matcher": {"first_token": ["foo"]}}])
    names = [p.name for p in eng._passes]
    assert "custom" in names
    assert "port_dir" not in names


def test_default_matches_config():
    """DEFAULT_CATEGORIES（代码内默认）与配置品类内容一致（防漂移）。"""
    from grammar.verilog.plugins.formatter import DEFAULT_CATEGORIES
    from core.config_registry import ConfigRegistry
    cfg = ConfigRegistry.get("formatter.categories")
    cfg_normalized = [
        {
            "name": c["name"],
            "enabled": c.get("enabled", True),
            "matcher": c.get("matcher", {}),
        }
        for c in cfg
    ]
    default_normalized = [
        {
            "name": c["name"],
            "enabled": c.get("enabled", True),
            "matcher": c.get("matcher", {}),
        }
        for c in DEFAULT_CATEGORIES
    ]
    assert cfg_normalized == default_normalized


def test_format_source_no_trailing_whitespace():
    """format_source 输出无行尾尾随空格（对齐冗余清理）。"""
    from core.define import DEFAULT_RULES_DIR
    from grammar.verilog.plugins.formatter import format_source
    src = "module m;\n    reg [31:0] a;\n    reg [31:0] bcd;\n    assign x = a;\nendmodule\n"
    out = format_source(src, DEFAULT_RULES_DIR)
    assert not any(l != l.rstrip() for l in out.split("\n"))
    # token 不丢
    def norm(s):
        return "".join("".join(l.split()) for l in s.splitlines())
    assert norm(out) == norm(src)


def test_style_loaded_from_config():
    """formatter.style（indent_width/max_line_width）从配置读取。"""
    from grammar.verilog.plugins.formatter.style import load_style
    style = load_style()
    assert style["indent_width"] == 4
    assert style["max_line_width"] == 100


def test_style_drives_indent_width(monkeypatch):
    """indent_width 配置驱动缩进宽度（build_engine 传参给 indent pass）。"""
    from grammar.verilog.plugins.formatter import build_engine
    from grammar.verilog.plugins.formatter import style as style_mod
    from grammar.verilog.plugins.formatter.boundary import LineContext

    # monkeypatch style.load_style 返回 indent_width=2（build_engine 内 from .style import）
    monkeypatch.setattr(style_mod, "load_style", lambda: {"indent_width": 2, "max_line_width": 100})

    eng = build_engine([])
    # 构造简单输入：module + 一级嵌套
    lines = ["module m;", "begin", "end", "endmodule"]
    ctxs = [
        LineContext(line_number=1, text="module m;", scope_depth=0),
        LineContext(line_number=2, text="begin", scope_depth=1),
        LineContext(line_number=3, text="end", scope_depth=0),
        LineContext(line_number=4, text="endmodule", scope_depth=0),
    ]
    out = eng.run(lines, ctxs)
    # begin 应缩进 2（indent_width=2 生效）
    assert out[1] == "  begin", f"indent_width=2 未生效: {out[1]!r}"
