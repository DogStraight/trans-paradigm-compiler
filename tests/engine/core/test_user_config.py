"""tests/engine/core/test_user_config.py — find_user_config 定位测试。

查找优先级（_user_config.find_user_config）：
    $TPC_CONFIG 显式 > CWD 向上（工作区隔离）> ~/.tpc/config.json（全局 profile）> ""
每个层级用 monkeypatch 隔离（env/CWD/全局路径），不依赖真实用户环境。
"""

import os

from core import _user_config


def test_env_override(tmp_path, monkeypatch):
    """$TPC_CONFIG 显式指定优先于工作区/全局。"""
    cfg = tmp_path / "env_config.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TPC_CONFIG", str(cfg))
    monkeypatch.chdir(tmp_path)
    assert _user_config.find_user_config() == str(cfg)


def test_workspace_precedes_global(tmp_path, monkeypatch):
    """工作区 config 优先于全局 profile（离 CWD 更近）。"""
    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    ws_cfg = ws / "config" / "tpc_config.json"
    ws_cfg.write_text("{}", encoding="utf-8")
    global_cfg = tmp_path / "global.json"
    global_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_user_config, "_GLOBAL_CONFIG", str(global_cfg))
    monkeypatch.delenv("TPC_CONFIG", raising=False)
    monkeypatch.chdir(ws)
    # 路径分隔符在 os.path.join 下可能混合（/ 与 \），规范化后比较
    got = os.path.normpath(_user_config.find_user_config())
    assert got == os.path.normpath(str(ws_cfg))


def test_global_profile_fallback(tmp_path, monkeypatch):
    """工作区无 config 时落到全局 profile（一次配置任意工作区享用）。"""
    ws = tmp_path / "ws"
    ws.mkdir()
    global_cfg = tmp_path / "global.json"
    global_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_user_config, "_GLOBAL_CONFIG", str(global_cfg))
    monkeypatch.delenv("TPC_CONFIG", raising=False)
    monkeypatch.chdir(ws)
    assert _user_config.find_user_config() == str(global_cfg)


def test_no_config_returns_empty(tmp_path, monkeypatch):
    """无 env、无工作区、无全局 → 空字符串（回退内建默认）。"""
    monkeypatch.delenv("TPC_CONFIG", raising=False)
    monkeypatch.setattr(
        _user_config, "_GLOBAL_CONFIG", str(tmp_path / "nonexistent.json")
    )
    monkeypatch.chdir(tmp_path)
    assert _user_config.find_user_config() == ""
