"""test_capabilities.py — 插件回调能力化（P2.5）：[capabilities] 声明 + 查找。

覆盖：能力声明解析（file.py:fn）、fail-fast（缺模块/缺函数/格式错）、
get_capability 查找、纯能力组件可发现、verilog 真实组件能力可用。
"""

import pytest

from core.plugin_loader import (
    _loaded_components,
    _load_capabilities,
    get_capability,
    load_all_components,
)


# ── 能力声明解析（file.py:fn） ──────────────────────────────


class TestLoadCapabilities:
    def test_parse_handler_spec(self, tmp_path):
        (tmp_path / "h.py").write_text(
            "def entry():\n    return {'k': 1}\n", encoding="utf-8"
        )
        caps = _load_capabilities(str(tmp_path), {"thing": "h.py:entry"})
        assert callable(caps["thing"])
        assert caps["thing"]() == {"k": 1}

    def test_missing_module_fail_fast(self, tmp_path):
        with pytest.raises(ValueError, match="模块不存在"):
            _load_capabilities(str(tmp_path), {"x": "nope.py:fn"})

    def test_missing_function_fail_fast(self, tmp_path):
        (tmp_path / "h.py").write_text("def other(): pass\n", encoding="utf-8")
        with pytest.raises(ValueError, match="函数 missing 不存在"):
            _load_capabilities(str(tmp_path), {"x": "h.py:missing"})

    def test_bad_spec_fail_fast(self, tmp_path):
        with pytest.raises(ValueError, match="格式应为"):
            _load_capabilities(str(tmp_path), {"x": "no_colon"})


# ── get_capability 查找 ─────────────────────────────────────


class TestGetCapability:
    def test_lookup_from_loaded_components(self, monkeypatch):
        fn = lambda: 42  # noqa: E731 — 测试桩
        monkeypatch.setitem(
            _loaded_components, "fake", {"capabilities": {"x": fn}}
        )
        assert get_capability("x") is fn
        assert get_capability("missing") is None

    def test_not_declared_returns_none(self):
        # 无任何能力声明的组件 → None（调用方降级，非报错）
        assert get_capability("__never_declared__") is None


# ── 纯能力组件发现 ──────────────────────────────────────────


class TestPureCapabilityComponent:
    def test_formatter_discovered(self):
        """formatter 无 [grammar]/[analyzer]/[transform] 声明，仅 [capabilities]
        + [formatter.*] 配置——应作为纯能力组件被加载。"""
        load_all_components()
        info = _loaded_components["formatter"]
        assert not info.get("grammar_files")
        assert not info.get("analyzer")
        assert not info.get("transform")
        assert callable(info["capabilities"]["formatter"])


# ── verilog 真实组件集成 ────────────────────────────────────


class TestVerilogCapabilities:
    def test_formatter_available(self):
        """verilog 插件经 load_all_components 加载后，formatter 能力应可用
        （format_generated 经能力接入）。typed_ports 的 transform_callbacks
        能力已随旧 analyze 原语链删除（P1.5 step 2——_ref_callbacks 不再产出）。"""
        load_all_components()
        f = get_capability("formatter")
        assert f is not None
        caps = f()
        for key in (
            "BoundaryScanner",
            "build_engine",
            "split_port_close_lines",
            "split_inst_tail_lines",
        ):
            assert callable(caps[key])

    def test_format_generated_via_capability(self):
        """format_generated 经能力查找格式化（format_output=True 管线 e2e 路径）。"""
        from pipeline import run_pipeline_on_source

        src = "module m;\n  assign a = b;\nendmodule\n"
        r = run_pipeline_on_source(
            source=src, quiet=True, no_lint=True, format_output=True
        )
        assert r["success"], r.get("error", "")
        assert r["output"]
