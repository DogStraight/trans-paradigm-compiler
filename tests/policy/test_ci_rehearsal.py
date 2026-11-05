"""tests/policy/test_ci_rehearsal.py — `tools/ci_rehearsal.py` 的判据与自检。

工具的价值在**结论三态不能退化成两态**：CI 只在推分支时跑，本地排练是打标前唯一的
自查手段，一旦它把"没验到"报成"绿"，就会制造"门禁已过"的假象（本仓已有实证教训：
449 个从未推送的提交上，门禁静默漂移到 4 类红）。

故这里只测**纯逻辑**（不真跑门禁——那是工具的本职，几分钟级，不进日常门禁）：
- 结论优先级：FAIL > INCOMPLETE > PASS；
- SKIP（本机无 pyright 等）**不算绿**；
- **零步骤**（筛选没命中）也不算绿——"没验" ≠ "验过了"；
- 步骤表与 `ci.yml` 对齐（含 pyright / wheel 两个易漏项）。
"""

import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import ci_rehearsal as cr  # noqa: E402  # pyright: ignore[reportMissingImports]


def _step(key: str) -> cr.Step:
    return next(s for s in cr.build_steps() if s.key == key)


def _row(key: str, verdict: str) -> tuple:
    return (_step(key), verdict, 0 if verdict == cr.PASS else 1, 1.0, "")


def test_step_table_mirrors_ci_yml() -> None:
    """步骤表覆盖 ci.yml 的每一项（含 pyright 与 wheel 两个易漏项）。"""
    keys = [s.key for s in cr.build_steps()]
    for expect in ("pytest", "smoke", "hardcode", "docrefs", "pyright", "edge", "fuzz",
                   "cli", "wheel"):
        assert expect in keys, f"步骤表缺 {expect}（与 ci.yml 脱节）"


def test_pyright_step_is_declared_with_pinned_project() -> None:
    """pyright 步骤存在且指向 strict 配置（不是空转）。"""
    assert _step("pyright").name.startswith("pyright")
    assert os.path.isfile(_ROOT / cr._PYRIGHT_PROJECT)
    assert cr.PYRIGHT_PIN.count(".") == 2, "pyright 版本应钉死（防默认规则漂移）"


def test_all_pass_is_pass() -> None:
    overall, matrix = cr.summarize([_row("pytest", cr.PASS), _row("pyright", cr.PASS)])
    assert overall == cr.PASS
    assert "PASS" in matrix


def test_any_fail_is_fail() -> None:
    """FAIL 优先于 SKIP：有真失败时不能报成 INCOMPLETE（会显得只是没验到）。"""
    overall, _ = cr.summarize([_row("pytest", cr.FAIL), _row("pyright", cr.SKIP)])
    assert overall == cr.FAIL


def test_skip_is_not_green() -> None:
    """SKIP（如本机没装 pyright）不算绿——整体只能 INCOMPLETE。"""
    overall, _ = cr.summarize([_row("pytest", cr.PASS), _row("pyright", cr.SKIP)])
    assert overall == "INCOMPLETE"


def test_zero_steps_is_not_green() -> None:
    """一步都没跑（筛选没命中）也必须 INCOMPLETE——「没验」不等于「验过了」。"""
    overall, matrix = cr.summarize([])
    assert overall == "INCOMPLETE"
    assert "未运行任何步骤" in matrix


def test_summarize_verdict_precedence_matrix() -> None:
    """三态组合的完整真值表（穷举，防以后加步骤时把优先级改坏）。"""
    cases = [
        ([cr.PASS], cr.PASS),
        ([cr.PASS, cr.PASS], cr.PASS),
        ([cr.PASS, cr.SKIP], "INCOMPLETE"),
        ([cr.SKIP, cr.SKIP], "INCOMPLETE"),
        ([cr.PASS, cr.FAIL], cr.FAIL),
        ([cr.FAIL, cr.SKIP], cr.FAIL),
        ([cr.FAIL, cr.FAIL], cr.FAIL),
    ]
    for verdicts, expect in cases:
        rows = [_row("pytest", v) for v in verdicts]
        overall, _ = cr.summarize(rows)
        assert overall == expect, f"{verdicts} → {overall}（应 {expect}）"


def test_every_ci_script_step_is_rehearsed() -> None:
    """`ci.yml` 里的每个 `python <脚本>` 必须在排练表里出现。

    实测代价（2026-11-05）：本文件 docstring 早就写着"步骤表与 ci.yml 对齐"，却
    没有判据——于是 `ci.yml` 加了 `check_invariants` 之后排练矩阵悄悄少跑一步，
    直到本轮新加 D2/D9 两个 ratchet 步骤才被发现。**写着对齐，不等于对齐会被抓。**
    """
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    scripts = sorted(set(re.findall(r"python ([A-Za-z0-9_./-]+\.py)", ci)))
    assert len(scripts) >= 6, f"ci.yml 只解析出 {scripts}，判据可能已失效"
    src = (_ROOT / "tools" / "ci_rehearsal.py").read_text(encoding="utf-8")
    missing = [s for s in scripts if s not in src]
    assert not missing, f"ci.yml 有排练表没覆盖的步骤：{missing}"
