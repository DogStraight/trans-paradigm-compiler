"""D7 断言强度 ratchet 守卫——弱断言占比只许降、不许无声增长。

本文件用 Python AST 扫描 ``tests/**/*.py``，统计三类"弱断言"：

1. **真值性**：``assert x`` / ``assert obj.attr`` / ``assert obj[key]`` /
   ``assert f()``，且表达式本身没有比较、没有 nullness 判据。
2. **非空**：``assert x.strip()``。这是"只要字符串非空"的最小形态；
   带具体期望值/长度的比较不在此列。
3. **仅 nullness**：单比较且一侧为 ``None`` 的 ``assert x is (not) None`` /
   ``assert x == None`` / ``assert x != None``。

**为什么剔除谓词调用**：``assert any(...)``、``assert isinstance(...)``、
``assert x.startswith(...)`` 等调用本身已经表达了可判定的谓词命题；把它们
算成"只断言真值"会制造假阳性，并诱导作者写成
``assert any(...) is True`` 这种更啰嗦、并未增强判据的形态。故本守卫对
固定的常见谓词名/前缀白名单放行；自定义函数默认不猜类型，宁可保守多计，
也不靠返回值猜"它是不是谓词"。

**为什么用比例而不是绝对数**：测试文件与断言数会自然增长；只看弱断言绝对
条数会让"新增强断言"也把守卫推向变红。比例看的是弱断言在断言总量中的
份额，增长测试面本身不会无故触发回归。

**扫描面与基线**：扫描 ``tests/**/*.py``（含测试文件里的 helper 断言），
排除 ``__pycache__`` 与本文件自身——否则守卫自己的断言会改变自己的分母。
本文件落地时实测：269 文件 / 2823 个测试函数 / 5164 个 assert；严格口径
弱断言 678 条（真值性 390、非空 3、仅 nullness 285），比例 13.13%。
阈值 = 基线 13.13% + 容差 0.50 个百分点。基线是 ratchet：只能通过增加
强断言或改写弱断言来降低比例，不能无声上调。
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_SELF = Path(__file__).resolve()
BASELINE_PCT = 13.13
TOLERANCE_PP = 0.50
MIN_FILES = 250
MIN_ASSERTS = 5000

# 固定白名单：不按返回值猜类型，避免"谓词类型推断"引入新的脆弱面。
# 前缀覆盖 is_*/has_* 这类常见布尔谓词 helper；未列出的自定义 helper
# 仍按"裸调用只断真值"保守计数。
PREDICATE_NAMES = frozenset({
    "any",
    "all",
    "isinstance",
    "issubclass",
    "hasattr",
    "callable",
    "startswith",
    "endswith",
    "match",
    "fullmatch",
    "search",
    "exists",
    "is_file",
    "isfile",
    "isdir",
    "isdigit",
})
PREDICATE_PREFIXES = ("is_", "has_", "_is_", "_has_")


def _called_name(call: ast.Call) -> str | None:
    """取调用名：``f()`` → ``f``；``obj.f()`` → ``f``。"""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_nullness(test: ast.expr) -> bool:
    """是否是单比较的仅 None 判据。"""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.comparators[0], ast.Constant):
        return False
    return (
        test.comparators[0].value is None
        and isinstance(test.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq))
    )


def _is_nonempty(test: ast.expr) -> bool:
    """是否是 ``assert x.strip()`` 这种只检查非空的形态。"""
    return isinstance(test, ast.Call) and _called_name(test) == "strip"


def _is_predicate_call(test: ast.expr) -> bool:
    """是否为白名单中的布尔谓词调用（真值性不计数）。"""
    if not isinstance(test, ast.Call):
        return False
    name = _called_name(test)
    if name is None:
        return False
    return name in PREDICATE_NAMES or name.startswith(PREDICATE_PREFIXES)


def _is_truthiness(test: ast.expr) -> bool:
    """是否是裸表达式真值断言（不含 ``not``；``not`` 是显式否定判据）。"""
    return isinstance(test, (ast.Name, ast.Attribute, ast.Subscript, ast.Call))


def _weak_kind(test: ast.expr) -> str | None:
    """返回 ``truthiness`` / ``nonempty`` / ``nullness``，强断言返回 None。"""
    if _is_nullness(test):
        return "nullness"
    if _is_nonempty(test):
        return "nonempty"
    if _is_truthiness(test) and not _is_predicate_call(test):
        return "truthiness"
    return None


def _test_files(root: Path):
    """按路径排序产出待扫描测试文件；跳过 __pycache__ 与守卫自身。"""
    for path in sorted((root / "tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.resolve() == _SELF:
            continue
        yield path


def scan(root: Path) -> dict[str, int]:
    """AST 扫描 ``root/tests``，返回文件/函数/断言及三类弱断言计数。"""
    stats = {
        "files": 0,
        "test_functions": 0,
        "asserts": 0,
        "weak": 0,
        "truthiness": 0,
        "nonempty": 0,
        "nullness": 0,
        "parse_errors": 0,
    }
    for path in _test_files(root):
        stats["files"] += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            stats["parse_errors"] += 1
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                stats["test_functions"] += 1
            if not isinstance(node, ast.Assert):
                continue
            stats["asserts"] += 1
            kind = _weak_kind(node.test)
            if kind is not None:
                stats["weak"] += 1
                stats[kind] += 1
    return stats


def _weak_pct(stats: dict[str, int]) -> float:
    """严格口径弱断言百分比；总断言为 0 时返回 0。"""
    total = stats["asserts"]
    return 100.0 * stats["weak"] / total if total else 0.0


def _exceeds_ratchet(stats: dict[str, int], baseline_pct: float, tolerance_pp: float) -> bool:
    """当前比例是否超过 ``基线 + 容差`` 个百分点。"""
    return _weak_pct(stats) > baseline_pct + tolerance_pp


def test_repo_strict_weak_ratio_within_ratchet() -> None:
    """真实仓库的严格弱断言比例不得超过基线 + 容差。"""
    stats = scan(ROOT)
    assert stats["parse_errors"] == 0
    assert stats["files"] >= MIN_FILES
    assert stats["asserts"] >= MIN_ASSERTS
    assert stats["weak"] > 0
    pct = _weak_pct(stats)
    limit = BASELINE_PCT + TOLERANCE_PP
    assert pct <= limit, (
        f"严格弱断言比例 {pct:.3f}% 超过 ratchet {limit:.2f}% "
        f"(基线 {BASELINE_PCT:.2f}% + 容差 {TOLERANCE_PP:.2f}pp)；"
        f"当前 weak={stats['weak']}/{stats['asserts']}，"
        f"truthiness={stats['truthiness']} nonempty={stats['nonempty']} "
        f"nullness={stats['nullness']}"
    )


def test_predicate_calls_are_excluded(tmp_path: Path) -> None:
    """any/isinstance/startswith/is_* 等谓词调用不算真值性弱断言。"""
    sample = tmp_path / "tests" / "test_sample.py"
    sample.parent.mkdir()
    sample.write_text(
        "def test_predicates():\n"
        "    values = [1]\n"
        "    assert any(values)\n"
        "    assert isinstance(values, list)\n"
        "    assert 'x'.startswith('x')\n"
        "    assert is_ready()\n"
        "    assert values\n",
        encoding="utf-8",
    )
    stats = scan(tmp_path)
    assert stats["asserts"] == 5
    assert stats["weak"] == 1
    assert stats["truthiness"] == 1


def test_three_weak_kinds_are_classified(tmp_path: Path) -> None:
    """三类弱断言各计一次，普通比较不计。"""
    sample = tmp_path / "tests" / "test_sample.py"
    sample.parent.mkdir()
    sample.write_text(
        "def test_mix():\n"
        "    assert value\n"
        "    assert text.strip()\n"
        "    assert result is not None\n"
        "    assert compute() == 1\n",
        encoding="utf-8",
    )
    stats = scan(tmp_path)
    assert stats["asserts"] == 4
    assert stats["truthiness"] == 1
    assert stats["nonempty"] == 1
    assert stats["nullness"] == 1
    assert stats["weak"] == 3


def test_one_new_weak_assertion_exceeds_ratchet(tmp_path: Path) -> None:
    """自证有效：在强断言样本里故意新增 1 条弱断言，判定函数必须返回超标。"""
    sample = tmp_path / "tests" / "test_sample.py"
    sample.parent.mkdir()
    strong = "def test_strong():\n    assert compute() == 1\n"
    sample.write_text(strong, encoding="utf-8")
    before = scan(tmp_path)

    sample.write_text(
        strong + "\ndef test_weak():\n    assert compute()\n",
        encoding="utf-8",
    )
    after = scan(tmp_path)

    assert before["asserts"] == 1
    assert before["weak"] == 0
    assert after["asserts"] == 2
    assert after["weak"] == 1
    assert _weak_pct(after) == 50.0
    assert _exceeds_ratchet(after, _weak_pct(before), TOLERANCE_PP)
