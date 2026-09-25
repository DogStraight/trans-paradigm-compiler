"""引擎能力协商契约（core/engine_compat.py + core/engine_capabilities.py）。

契约：语言包 `grammar/<lang>/tpc.toml` 声明

    [engine]
    uses = ["lexer.token_ext.v1", "parser.pratt.v1"]

逐项协商（能力表与版本语义见 `core/engine_capabilities.py`）；任一项不认识或版本
不匹配 → 加载 fail-fast（ConfigError，**点名是哪一项**）；未声明 `[engine]` = 不校验
（纯增量，ad-hoc 包与测试夹具不受影响）。

本文件覆盖：形态合法性、协商语义（**未声明的能力变化不误伤**）、旧 `api` 线已删除
（残留即报未知键）、`[engine]` 不进配置声明。

Doc: core/config_lifecycle.md（包↔引擎契约节）
"""
from __future__ import annotations

import os

import pytest

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from core import engine_capabilities as caps  # noqa: E402
from core.config_registry import _load_meta_declarations  # noqa: E402
from core.engine_compat import check_engine_compat  # noqa: E402
from core.errors import ConfigError  # noqa: E402

pytestmark = pytest.mark.smoke  # smoke：core 组代表（包/引擎契约 fail-fast）

_ANY = sorted(caps.CAPABILITIES)[0]  # 任取一项真实能力
_ANY_V = f"{_ANY}.v{caps.CAPABILITIES[_ANY]}"


# ── parse_use 形态 ──────────────────────────────────────────

def test_parse_use_splits_name_and_version():
    assert caps.parse_use("lexer.token_ext.v1") == ("lexer.token_ext", "1")
    assert caps.parse_use("capability.elaborator.v2") == ("capability.elaborator", "2")


@pytest.mark.parametrize("bad", ["lexer.token_ext", "lexer.token_ext.v", ".v1", "", 1])
def test_parse_use_rejects_malformed(bad):
    with pytest.raises(ConfigError, match="uses 项"):
        caps.parse_use(bad)


# ── check_engine_compat 各态 ────────────────────────────────

def test_absent_engine_section_is_not_checked():
    """未声明 [engine] → 不校验（纯增量，不破坏既有包/夹具）。"""
    check_engine_compat({}, "grammar/x")


def test_valid_uses_passes():
    check_engine_compat({"engine": {"uses": [_ANY_V]}}, "grammar/x")


def test_all_current_capabilities_pass():
    check_engine_compat(
        {"engine": {"uses": [f"{k}.v{v}" for k, v in caps.CAPABILITIES.items()]}},
        "grammar/x",
    )


def test_unknown_capability_reports_its_name():
    """引擎不认识的能力 → 报错**点名**是哪一项（旧契约说不出缺什么）。"""
    with pytest.raises(ConfigError, match="不认识能力 'no.such.thing'"):
        check_engine_compat({"engine": {"uses": ["no.such.thing.v1"]}}, "grammar/x")


def test_version_mismatch_names_item_and_both_versions():
    with pytest.raises(ConfigError, match=rf"能力 '{_ANY}'.*声明 v99.*v\d"):
        check_engine_compat({"engine": {"uses": [f"{_ANY}.v99"]}}, "grammar/x")


def test_legacy_api_key_is_rejected():
    """旧契约 `api` 已删除——残留必须**响亮失败**，不得静默忽略。"""
    with pytest.raises(ConfigError, match="未知键: api"):
        check_engine_compat({"engine": {"api": "0.1"}}, "grammar/x")


@pytest.mark.parametrize(
    "section", [{}, [], {"uses": []}, {"uses": "x"}, "0.1", {"uses": [1]}]
)
def test_malformed_engine_section_fails(section):
    with pytest.raises(ConfigError):
        check_engine_compat({"engine": section}, "grammar/x")


# ── 协商语义：未声明的能力变化不误伤（P-C 的核心承诺） ──────

def test_unrelated_capability_change_does_not_affect_pack(monkeypatch):
    """包只声明 A；引擎把**另一项** B 升版 → 该包**照旧可加载**。

    这正是能力协商相对"整条 API 线"的收益：受影响面 = 声明了该能力的包。
    """
    names = sorted(caps.CAPABILITIES)
    mine, other = names[0], names[1]
    monkeypatch.setitem(caps.CAPABILITIES, other, "99")
    check_engine_compat({"engine": {"uses": [f"{mine}.v1"]}}, "grammar/x")


def test_declared_capability_change_is_caught(monkeypatch):
    """引擎把包**声明过**的能力升版 → 该包被拦下（且点名）。"""
    name = sorted(caps.CAPABILITIES)[0]
    monkeypatch.setitem(caps.CAPABILITIES, name, "99")
    with pytest.raises(ConfigError, match=rf"能力 '{name}'"):
        check_engine_compat({"engine": {"uses": [f"{name}.v1"]}}, "grammar/x")


# ── [engine] 不是配置声明（不进配置中心） ───────────────────

def test_engine_section_is_not_a_config_declaration(tmp_path):
    pack = tmp_path
    (pack / "tpc.toml").write_text(
        f'[engine]\nuses = ["{_ANY_V}"]\n\n[lexer]\nk = {{ file = "x.toml" }}\n',
        encoding="utf-8",
    )
    decls = _load_meta_declarations(grammar_dir=str(pack))
    assert not any(d[0].startswith("engine") for d in decls), (
        "[engine] 是包↔引擎契约，不应进配置中心"
    )
    assert any(d[0] == "lexer.k" for d in decls)


# ── 内置三包：能力清单由清单推导（权威判据在 policy 门禁） ──

@pytest.mark.parametrize("pack", ["c4", "verilog", "yaml"])
def test_builtin_packs_declare_uses_and_negotiate(pack):
    """内置三包都声明能力清单且逐项协商通过。

    ⚠ "推导集 ⊆ 声明集"（用到了就必须声明）是**仓库不变式**，断言在
    `tests/policy/test_engine_capabilities.py`——同一断言两处写就成了新的散点。
    """
    import tomllib

    with open(os.path.join(_ROOT, "grammar", pack, "tpc.toml"), "rb") as f:
        meta = tomllib.load(f)
    assert meta["engine"]["uses"], f"{pack} 未声明能力清单"
    check_engine_compat(meta, f"grammar/{pack}")
