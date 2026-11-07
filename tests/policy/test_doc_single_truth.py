"""单一真相门禁：README / PROGRESS / ROADMAP 不得复述随轮变动的数字。

背景（作者 2026-11-07）：这三份文档每轮收口都被同步改一遍，同一事实（版本、
测试数、结构分、提交号）在多处各写一份 ⇒ 真相不唯一，且必然漂移——实例：README
曾写 C 包"C99 接受清单 27 条 / 25 条入 AST"，与 `grammar/c/README.md` 的
"42 条 / 接受 40 / 空洞 2"矛盾（后者才是现算的唯一来源）。

规则与全表见 `docs/README.md`「单一真相（更新规律）」：
- 版本号 → `pyproject.toml` + `core/__init__.py`（测试锁定）
- 刻度/收口状态 → `PROGRESS.md`
- 逐轮变更 + 验证数字/提交号 → `CHANGELOG.md`
- 其他位置**只许指向**，不许复制。

本门禁只抓机械可判的复述形态（测试计数 / 结构分 / 提交号 / README 版本号）；
"这段该不该是指针"仍由人判（同 `test_doc_stats.py` 的取舍：误报会诱发无谓改写）。
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

#: 文件 → [(正则, 该数字的唯一来源)]。README 额外禁版本号（版本源在 pyproject）。
_BANNED: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "README.md": [
        (re.compile(r"\b\d+\s+passed\b"), "测试计数（CHANGELOG 当轮条目）"),
        (re.compile(r"\bS\s*=\s*\d+"), "结构欠账分（CHANGELOG 当轮条目）"),
        (re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"), "提交号（CHANGELOG / git log）"),
        (re.compile(r"\b\d+\.\d+\.\d+\b"), "版本号（pyproject.toml + core/__init__.py）"),
        (re.compile(r"Last synced", re.IGNORECASE), "手工同步日期（事实新鲜度由单一来源保证）"),
    ],
    "PROGRESS.md": [
        (re.compile(r"\b\d+\s+passed\b"), "测试计数（CHANGELOG 当轮条目）"),
        (re.compile(r"\bS\s*=\s*\d+"), "结构欠账分（CHANGELOG 当轮条目）"),
        (re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"), "提交号（CHANGELOG / git log）"),
    ],
    "ROADMAP.md": [
        (re.compile(r"\b\d+\s+passed\b"), "测试计数（CHANGELOG 当轮条目）"),
        (re.compile(r"\bS\s*=\s*\d+"), "结构欠账分（CHANGELOG 当轮条目）"),
        (re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"), "提交号（CHANGELOG / git log）"),
    ],
}

#: 指向关系（结构性兜底）：README/PROGRESS/ROADMAP 必须给出各自的上游指针。
_POINTERS: dict[str, tuple[str, ...]] = {
    "README.md": ("PROGRESS.md", "CHANGELOG.md"),
    "PROGRESS.md": ("CHANGELOG.md",),
    "ROADMAP.md": ("PROGRESS.md", "CHANGELOG.md"),
}


def _text(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _violations(rel: str) -> list[str]:
    """该文件正文里命中的禁用模式（行号 + 事实归属）。"""
    found: list[str] = []
    for lineno, line in enumerate(_text(rel).splitlines(), 1):
        for pattern, owner in _BANNED[rel]:
            match = pattern.search(line)
            if match:
                found.append(
                    f"{rel}:{lineno} 复述「{match.group(0)}」——该事实唯一来源：{owner}"
                )
    return found


def test_no_restated_volatile_facts() -> None:
    """README / PROGRESS / ROADMAP 不得复述随轮变动的数字与提交号。"""
    problems = [item for rel in _BANNED for item in _violations(rel)]
    assert not problems, (
        "以下位置复述了别处拥有的真相，请改成指向唯一来源（见 docs/README.md"
        "「单一真相」）：\n  " + "\n  ".join(problems)
    )


def test_docs_own_the_pointer_map() -> None:
    """规则必须落档：`docs/README.md` 含「单一真相」表，否则门禁无依据。"""
    nav = _text("docs/README.md")
    assert "单一真相" in nav
    for owner in ("PROGRESS.md", "CHANGELOG.md", "pyproject.toml"):
        assert owner in nav, f"docs/README.md 的单一真相表未指向 {owner}"


def test_targets_exist() -> None:
    """被纳管文件必须存在——路径写错会让扫描静默空转（假绿）。"""
    missing = [rel for rel in _BANNED if not (_ROOT / rel).is_file()]
    assert not missing, f"纳管文件不存在（路径写错？）：{missing}"


def test_patterns_match_known_samples() -> None:
    """模式自证：典型复述串必须仍被命中（正则失效 = 门禁假绿）。"""
    samples = {
        "README.md": [
            "全量 4502 passed / 7 skipped",
            "结构分 S = 833",
            "提交 `8b5a80a` 收口",
            "Version 0.1.2",
            "Last synced against the codebase: 2026-11-03",
        ],
        "PROGRESS.md": ["全量 4502 passed", "S = 1013", "见 `291e8ff`"],
        "ROADMAP.md": ["pytest 1956 passed", "S = 1110", "commit `a1b2c3d`"],
    }
    for rel, texts in samples.items():
        for text in texts:
            assert any(p.search(text) for p, _ in _BANNED[rel]), (
                f"自检失败：{rel} 的 {text!r} 未被任何模式命中——模式已失效"
            )


def test_patterns_ignore_legitimate_tokens() -> None:
    """反向自检：版本标签、语言名、规则码等合法文本不得被误判（误报比漏报更伤）。"""
    legitimate = {
        "README.md": [
            "Python 3.11+",
            "`grammar/c4/` turns a C subset into VM assembly",
            "IEEE 1364-2005",
            "the `c11`/`c17`/`c23` plugins",
        ],
        "PROGRESS.md": [
            "主线 2（0.1.4）",
            "块 7 = 解析层片段级",
            "T1–T3（#51–#66）",
        ],
        "ROADMAP.md": [
            "v0.2 候选",
            "P2.3 backlog",
            "c4 定位",
        ],
    }
    for rel, texts in legitimate.items():
        for text in texts:
            hits = [p.pattern for p, _ in _BANNED[rel] if p.search(text)]
            assert not hits, f"误报：{rel} 的 {text!r} 被判为复述（命中 {hits}）"


def test_pointer_targets_are_given() -> None:
    """结构性兜底：每份文档都必须写出自己的上游指针（不能只删不复述）。"""
    for rel, owners in _POINTERS.items():
        text = _text(rel)
        missing = [owner for owner in owners if owner not in text]
        assert not missing, (
            f"{rel} 缺少指向 {missing} —— 删掉复述后必须留指针，否则读者找不到真相"
        )
