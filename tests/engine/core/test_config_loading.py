"""配置加载防护单元测试 — malformed TOML / 缺段 / 可选缺失。

固化 token.toml 重复 key 事故的防护契约：
    - required=False 的文件，TOML 语法损坏（重复 key 等）→ ConfigError（fail-fast，
      不能再静默退化成空表导致"全部 token 变 id"的静默错乱）
    - 文件存在但缺声明的 section → ConfigError（配置声明错误）
    - 可选文件缺失 → 容忍（合法的可选缺失）
"""

import os
import pytest

from core.errors import ConfigError
from core.config_registry import ConfigRegistry, _load_meta_declarations


@pytest.fixture
def isolated_registry(tmp_path):
    """隔离 ConfigRegistry：保存/恢复全局注册表状态，避免破坏 conftest 的共享配置。"""
    saved = (
        dict(ConfigRegistry._entries),
        dict(ConfigRegistry._loaded),
        ConfigRegistry._resolved,
    )
    ConfigRegistry.reset()
    yield tmp_path
    ConfigRegistry._entries = saved[0]
    ConfigRegistry._loaded = saved[1]
    ConfigRegistry._resolved = saved[2]


def _declare_and_load(
    root,
    name,
    fname,
    *,
    section=None,
    required=False,
):
    ConfigRegistry.declare(
        name, file=fname, section=section, required=required, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))


def test_malformed_toml_fails_fast_even_optional(isolated_registry):
    """可选文件（required=False）含重复 key → ConfigError（incident 场景）。"""
    root = isolated_registry
    (root / "bad_dup.toml").write_text(
        '[id.keyword]\nmodule = "module"\nmodule = "module"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="TOML 语法错误"):
        _declare_and_load(root, "t.baddup", "bad_dup.toml", required=False)


def test_missing_declared_section_fails_fast(isolated_registry):
    """文件存在但缺声明的 section → ConfigError（不再静默 data.get(section, {})）。"""
    root = isolated_registry
    (root / "bad_section.toml").write_text('[other]\nx = 1\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="缺少声明段"):
        _declare_and_load(
            root, "t.badsect", "bad_section.toml", section="missing_sec", required=False
        )


def test_optional_missing_file_tolerated(isolated_registry):
    """可选文件缺失是合法状态 → 容忍，加载为空 dict，不报错。"""
    root = isolated_registry
    ConfigRegistry.declare(
        "t.okmissing", file="nope.toml", required=False, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._loaded.get("t.okmissing") == {}


def test_required_missing_file_fails_fast(isolated_registry):
    """必选文件缺失 → ConfigError（原有契约保持）。"""
    root = isolated_registry
    with pytest.raises(ConfigError, match="No such file|未找到|找不到"):
        _declare_and_load(root, "t.reqmiss", "nope.toml", required=True)


# ── 来源追踪（config dump 基础） ──────────────────────────


def test_sources_recorded_on_load(isolated_registry):
    """load_all 后 _sources 记录每个 key 的实际文件 + section。"""
    root = isolated_registry
    (root / "src.toml").write_text(
        '[number]\nbased = [1, 2]\n[other]\nx = 1\n', encoding="utf-8"
    )
    ConfigRegistry.declare(
        "t.src1", file="src.toml", section="number", required=True, base="temp"
    )
    ConfigRegistry.declare(
        "t.src2", file="src.toml", required=True, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._sources["t.src1"] == {
        "file": str(root / "src.toml").replace("\\", "/"),
        "section": "number",
    }
    assert ConfigRegistry._sources["t.src2"]["section"] is None


def test_sources_bare_and_missing(isolated_registry):
    """bare data 与缺失文件在 sources 中正确标记。"""
    root = isolated_registry
    ConfigRegistry.declare("t.bare", file="", bare_value=[1, 2, 3])
    ConfigRegistry.declare("t.miss", file="nope.toml", required=False, base="temp")
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._sources["t.bare"] == {"bare": True}
    assert ConfigRegistry._sources["t.miss"]["missing"] is True


def test_resolve_with_sources_returns_pair(isolated_registry):
    """resolve_with_sources 返回 (loaded, sources)，resolve 保持返回 dict。"""
    root = isolated_registry
    (root / "r.toml").write_text('[sec]\na = 1\n', encoding="utf-8")
    ConfigRegistry.declare(
        "t.r", file="r.toml", section="sec", required=True, base="temp"
    )
    loaded, sources = ConfigRegistry.resolve_with_sources(
        str(root), temp_dir=str(root)
    )
    assert loaded["t.r"] == {"a": 1}
    assert sources["t.r"]["section"] == "sec"
    # resolve 兼容：仍返回 dict
    r = ConfigRegistry.resolve(str(root), temp_dir=str(root))
    assert isinstance(r, dict)


# ── 声明结构校验（schema 化第一步） ──────────────────────


def _write_tpc(tmp_path, content):
    (tmp_path / "tpc.toml").write_text(content, encoding="utf-8")


def test_decl_unknown_field_rejected(tmp_path):
    """声明含未知字段 → ConfigError（fail-fast）。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = "x.toml", typo = 1 }\n')
    with pytest.raises(ConfigError, match="未知字段"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_missing_file_rejected(tmp_path):
    """dict 含声明字段但缺 file → ConfigError（疑似忘了 file）。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { section = "x" }\n')
    with pytest.raises(ConfigError, match="缺 file"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_file_type_rejected(tmp_path):
    """file 类型错误（非 str/list）→ ConfigError。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = 123 }\n')
    with pytest.raises(ConfigError, match="file 必须是字符串"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_required_type_rejected(tmp_path):
    """required 类型错误（非 bool）→ ConfigError。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = "x.toml", required = "yes" }\n')
    with pytest.raises(ConfigError, match="required 必须是布尔值"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_valid_bare_and_file_accepted(tmp_path):
    """合法 bare data 与文件式声明通过校验。"""
    _write_tpc(
        tmp_path,
        '[analyzer]\nprimitives = ["a", "b"]\n'
        '[lexer]\nok = { file = "x.toml", section = "s", required = false }\n',
    )
    decls = _load_meta_declarations(grammar_dir=str(tmp_path))
    names = [d[0] for d in decls]
    assert "analyzer.primitives" in names
    assert "lexer.ok" in names
