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
    assert "inst_port" == names[-1]


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
