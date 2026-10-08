"""规划文件容量门禁 —— 待办/边界/决策登记不得无界增长。

动机（2026-10-08 收口轮实测）：TODO.md 397 行 / ROADMAP.md 498 行 /
`gap-language-pack-scope.md` 427 行——正文里大量是"已完成的过程叙述"与
与测试/CHANGELOG 重复的复述，真正的未完成项被稀释，读文件的人要从历史里
挑事实。解法不是"下次记得删"，而是给每份规划/登记文件一个**容量上限**：
超限即红，逼着先删旧再进新（与 `policy/structural_budget.md` 同姿态：
口径显式、只许显式调整）。

口径（三条，都是刻意的）：
- **上限不是目标**：数字按收口后实测留余量（见 `_ROOT_BUDGETS` /
  `_GLOB_BUDGETS` 注释），触顶说明该删旧条目，或把"现状边界"搬去
  `docs/gaps/`、"过程叙述"搬去 git log。
- **按目录模式纳管**（gaps/*.md、decisions/*.md）：新档一进来就受同一预算
  约束，不需要"记得加一行清单"。根文件（TODO/ROADMAP/DRAFT）显式列出。
- **缺席不算违规**：`DRAFT.md` 清空后按纪律删除——门禁只查存在的文件。

自检：`test_synthetic_violation_is_caught` 用临时目录反证"超限真的会红"
（防口径写错后恒绿），并反证未超限文件不误报。

Doc: policy/doc-alignment.md
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 根文件行数上限：收口后实测 + 余量（TODO 160 / ROADMAP 320 / DRAFT 70）。
# 提高这些数字 = 显式决策（改这里）。
_ROOT_BUDGETS: tuple[tuple[str, int], ...] = (
    ("TODO.md", 160),
    ("ROADMAP.md", 320),
    ("DRAFT.md", 70),
)
# 登记类目录：单档上限（gap 200 / ADR 150）。
_GLOB_BUDGETS: tuple[tuple[str, int], ...] = (
    ("docs/gaps/gap-*.md", 200),
    ("docs/decisions/[0-9]*.md", 150),
)
# 决策档"≤10 决策点"是 docs/README.md 的既定纪律（这里给门禁化）。
_ADR_DIR = "docs/decisions"
_ADR_LIMIT = 10


def _line_count(path: Path) -> int:
    """文件行数（末行无换行也算一行）。"""
    return len(path.read_text(encoding="utf-8").splitlines())


def _violations(root: Path) -> list[str]:
    """规划文件超限清单（缺席文件跳过：DRAFT.md 清空即删属正常态）。"""
    found: list[str] = []
    for rel, limit in _ROOT_BUDGETS:
        path = root / rel
        if path.is_file():
            lines = _line_count(path)
            if lines > limit:
                found.append(f"{rel}: {lines} 行 > 上限 {limit}")

    for pattern, limit in _GLOB_BUDGETS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            lines = _line_count(path)
            if lines > limit:
                rel = path.relative_to(root).as_posix()
                found.append(f"{rel}: {lines} 行 > 上限 {limit}")

    adr_dir = root / _ADR_DIR
    if adr_dir.is_dir():
        count = len([p for p in adr_dir.glob("[0-9]*.md") if p.is_file()])
        if count > _ADR_LIMIT:
            found.append(f"{_ADR_DIR}: {count} 份 ADR > 上限 {_ADR_LIMIT}")
    return found


def test_planning_docs_within_budget() -> None:
    """规划/登记文件不得超容量——超限请先删旧条目或搬去 gaps/ROADMAP。"""
    violations = _violations(_ROOT)
    assert not violations, (
        "规划文件超容量上限（先删旧条目/搬出现状边界，再进新内容；"
        "确需提高上限请显式改 `tests/policy/test_planning_doc_budget.py`）：\n  "
        + "\n  ".join(violations)
    )


def test_budget_targets_exist() -> None:
    """常驻规划文件路径写错会让检查静默空转（假绿）。

    `DRAFT.md` 允许缺席（清空即删），故只要求 TODO/ROADMAP 在位。
    """
    missing = [
        rel
        for rel, _ in _ROOT_BUDGETS
        if rel != "DRAFT.md" and not (_ROOT / rel).is_file()
    ]
    assert not missing, f"容量门禁纳管的常驻文件不存在（路径写错？）：{missing}"


def test_synthetic_violation_is_caught(tmp_path: Path) -> None:
    """反向自检：超限形态必须被 _violations 抓到（防口径恒绿），且不误报。"""
    (tmp_path / "TODO.md").write_text("x\n" * 3, encoding="utf-8")
    (tmp_path / "DRAFT.md").write_text("x\n" * 999, encoding="utf-8")
    gaps = tmp_path / "docs" / "gaps"
    gaps.mkdir(parents=True)
    (gaps / "gap-demo.md").write_text("x\n" * 999, encoding="utf-8")
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    for i in range(_ADR_LIMIT + 1):
        (decisions / f"{i:04d}-demo.md").write_text("x\n" * 999, encoding="utf-8")

    found = _violations(tmp_path)
    joined = "\n".join(found)
    assert "DRAFT.md" in joined and "gap-demo.md" in joined
    assert "0000-demo.md" in joined and f"> 上限 {_ADR_LIMIT}" in joined
    # 未超限的 TODO.md 不得误报（门禁误报比漏报更伤）
    assert not any(line.startswith("TODO.md") for line in found)
    # docs 目录缺席时不得崩（只查存在的文件）
    assert _violations(tmp_path / "nonexistent") == []
