"""引擎 API 兼容契约（core/engine_compat.py）——语言包 [engine] api 声明。

契约：语言包 `grammar/<lang>/tpc.toml` 声明

    [engine]
    api = "0.1"      # 该包构建所依据的引擎 API 线（major.minor）

引擎 major.minor 不匹配 → 加载 fail-fast（ConfigError）；未声明 = 不校验
（纯增量，ad-hoc 包与测试夹具不受影响）。三条断言：声明齐全 / 不匹配拦截 /
该段不进配置声明（否则会被当 bare data 注册）。
"""

import os
import tomllib

import pytest

from core import __version__
from core.errors import ConfigError
from core.engine_compat import api_line, check_engine_compat, engine_api_line
from core.config_registry import _load_meta_declarations

pytestmark = pytest.mark.smoke  # smoke：core 组代表（包/引擎契约 fail-fast）

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


# ── 版本串解析 ──────────────────────────────────────


def test_api_line_takes_major_minor():
    assert api_line("0.1.1") == "0.1"
    assert api_line("2.3") == "2.3"


def test_api_line_rejects_short_version():
    with pytest.raises(ConfigError, match="major.minor"):
        api_line("0")


def test_engine_api_line_matches_package_version():
    assert engine_api_line() == api_line(__version__)


# ── check_engine_compat 各态 ────────────────────────


def test_absent_section_is_not_checked():
    """未声明 [engine] → 不校验（纯增量，不破坏既有包/夹具）。"""
    check_engine_compat({}, "grammar/x")


def test_matching_api_passes():
    check_engine_compat({"engine": {"api": api_line(__version__)}}, "grammar/x")


def test_mismatched_api_fails_fast():
    with pytest.raises(ConfigError, match="不兼容"):
        check_engine_compat({"engine": {"api": "9.9"}}, "grammar/x")


def test_section_without_key_fails_fast():
    with pytest.raises(ConfigError, match="缺"):
        check_engine_compat({"engine": {}}, "grammar/x")


def test_non_string_api_fails_fast():
    with pytest.raises(ConfigError, match="非空字符串"):
        check_engine_compat({"engine": {"api": 1}}, "grammar/x")


def test_non_table_section_fails_fast():
    with pytest.raises(ConfigError, match="须为表"):
        check_engine_compat({"engine": "0.1"}, "grammar/x")


# ── 集成：tpc.toml 加载路径 ─────────────────────────


def _write_tpc(tmp_path, content):
    (tmp_path / "tpc.toml").write_text(content, encoding="utf-8")


def test_pack_with_mismatched_engine_fails_fast(tmp_path):
    _write_tpc(
        tmp_path, '[engine]\napi = "9.9"\n\n[lexer]\nk = { file = "x.toml" }\n'
    )
    with pytest.raises(ConfigError, match="不兼容"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_pack_without_engine_section_still_loads(tmp_path):
    _write_tpc(tmp_path, '[lexer]\nk = { file = "x.toml" }\n')
    decls = _load_meta_declarations(grammar_dir=str(tmp_path))
    assert any(d[0] == "lexer.k" for d in decls)


def test_engine_section_not_registered_as_config(tmp_path):
    """[engine] 是包↔引擎契约，不是配置声明（不应进配置中心）。"""
    _write_tpc(
        tmp_path,
        f'[engine]\napi = "{api_line(__version__)}"\n\n'
        '[lexer]\nk = { file = "x.toml" }\n',
    )
    decls = _load_meta_declarations(grammar_dir=str(tmp_path))
    assert not any(d[0].startswith("engine") for d in decls)
    assert any(d[0] == "lexer.k" for d in decls)


@pytest.mark.parametrize("pack", ["grammar/verilog", "grammar/c4", "grammar/yaml"])
def test_builtin_packs_declare_current_engine_line(pack):
    """内置三包都声明 [engine].api = 当前引擎线。

    引擎 minor 变更时本测试会失败——这是**故意的**：契约要求同步复核三包，
    确认它们确实与新引擎语义兼容后再改声明。
    """
    with open(os.path.join(_ROOT, pack, "tpc.toml"), encoding="utf-8") as f:
        meta = tomllib.loads(f.read())
    assert meta.get("engine", {}).get("api") == engine_api_line()
