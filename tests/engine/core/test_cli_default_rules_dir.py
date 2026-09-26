"""tests/engine/core/test_cli_default_rules_dir.py — CLI 默认 rules_dir 必须与 CWD 无关。

事故（2026-09-26 发布冒烟实测，wheel 装好后从仓库外跑）：

    tpc format   …                  → 正常（走 `_resolve_grammar_dirs()`）
    tpc config dump                 → ConfigError: glob 未找到匹配文件: 0*/*.toml

成因：`_cmd_config_dump` 的默认值是**相对**的 `DEFAULT_RULES_DIR`（`grammar/verilog`），
没有像 `_resolve_grammar_dirs()` 那样 `os.path.join(_project_root, …)` ⇒ 解析结果依赖
CWD；CWD 落在仓库外时那条相对路径不存在，于是只剩内置默认声明、规则 glob 落空。

判据：把 CWD 换到别处后调用同一条指令，**必须仍解析到项目内的语言包**。
（`--rules-dir` 显式给路径时不在此列：显式路径按常规相对 CWD 解析。）
"""

import argparse
import os

import main
from core.define import DEFAULT_RULES_DIR


def _dump_args(rules_dir=None):
    return argparse.Namespace(rules_dir=rules_dir, json=False, pretty=False)


def test_config_dump_default_rules_dir_is_cwd_independent(tmp_path, monkeypatch, capsys):
    """CWD 换到临时目录后，默认仍解析到 `_project_root` 下的语言包。"""
    monkeypatch.chdir(tmp_path)

    main._cmd_config_dump(_dump_args())

    out = capsys.readouterr().out
    expected = os.path.join(main._project_root, DEFAULT_RULES_DIR)
    assert f"# Config dump — {expected}" in out, (
        f"默认 rules_dir 未锚定 _project_root：期望输出含 {expected!r}，实际首行 "
        f"{out.splitlines()[:1]!r}"
    )


def test_config_dump_explicit_rules_dir_still_honored(tmp_path, monkeypatch, capsys):
    """显式 `--rules-dir`（绝对路径）照旧生效——修默认值不改显式路径语义。"""
    monkeypatch.chdir(tmp_path)
    explicit = os.path.join(main._project_root, "grammar", "c4")

    main._cmd_config_dump(_dump_args(rules_dir=explicit))

    out = capsys.readouterr().out
    assert f"# Config dump — {explicit}" in out
