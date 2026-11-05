"""控制台自护必须单点：`reconfigure(` 只允许出现在 `core/console.py`。

背景（审计 2026-11-05 复核）：抽离后仍有 6 处目录副本；这里加"副本不许再长"的
allowlist + stale 门禁——新副本出现即红；allowlist 中登记的文件若不再命中（已删/改名）
同样红（防允许清单腐化）。
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (
    "core", "lexer", "parser", "linter", "analyzer", "transform", "renderer",
    "pipeline", "preprocessor", "policy", "tools", "tests", "islands",
)
_SINGLE_POINT = "core/console.py"
#: 允许清单：路径 → 理由（新增副本必须在这里登记并由 reviewer 判，不能默默加）
_ALLOW: dict[str, str] = {}


def _reconfigure_calls(path: Path) -> list[int]:
    """AST 级：只认 `xxx.reconfigure(...)` 调用（注释/字符串里的字样不算）。"""
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconfigure"
    ]


def _hits() -> dict[str, list[int]]:
    hits: dict[str, list[int]] = {}
    paths = [p for d in _SCAN_DIRS for p in (_ROOT / d).rglob("*.py")]
    main = _ROOT / "main.py"
    if main.is_file():
        paths.append(main)
    for path in paths:
        lines = _reconfigure_calls(path)
        if lines:
            hits[path.relative_to(_ROOT).as_posix()] = lines
    return hits


def test_reconfigure_only_in_single_point():
    """副本不许再长：除单点外任何 `.py` 出现 `reconfigure(` 即红。"""
    hits = {k: v for k, v in _hits().items() if k not in _ALLOW}
    bad = {k: v for k, v in hits.items() if k != _SINGLE_POINT}
    assert not bad, (
        "控制台自护副本出现在单点之外（应改调用 core/console.py::ensure_utf8_stdio）：\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(bad.items()))
    )


def test_allowlist_entries_still_hit():
    """stale 检测：allowlist 登记的文件必须仍命中（删了/改名了就要清理登记）。"""
    hits = _hits()
    stale = [k for k in _ALLOW if k not in hits]
    assert not stale, f"allowlist 已失效（文件不再命中 reconfigure）：{stale}"
