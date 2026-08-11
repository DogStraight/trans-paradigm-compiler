"""配置加载防护单元测试 — malformed TOML / 缺段 / 可选缺失。

固化 2026-08-09 token.toml 重复 key 事故的防护契约：
    - required=False 的文件，TOML 语法损坏（重复 key 等）→ ConfigError（fail-fast，
      不能再静默退化成空表导致"全部 token 变 id"的静默错乱）
    - 文件存在但缺声明的 section → ConfigError（配置声明错误）
    - 可选文件缺失 → 容忍（合法的可选缺失）
"""

import os
import pytest

from core.errors import ConfigError
from core.config_registry import ConfigRegistry


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
