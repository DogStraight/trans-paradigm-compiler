"""控制台自护必须单点：`reconfigure(` 只允许出现在 `core/console.py`。

背景（审计 2026-11-05 抽离轮；2026-11-07 外部证伪 F5 修正）：
- 抽离后仍有副本 → allowlist + stale 门禁（新副本出现即红；登记文件不再命中同样红）；
- **扫描面 = 全仓递归**（旧版只扫固定目录清单，`packaging/`、根级入口等新目录
  天然漏网）——排除区只有 VCS/缓存/草稿/构建产物；
- **解析失败不许静默跳过**（旧版 `except SyntaxError: return []` 等于"读不了的
  文件自动通过"；门禁无法证明它没有副本时应当 fail-closed）。
"""

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
#: 排除区：VCS / 虚拟环境 / 缓存 / 构建产物 / 作者草稿（非产品面）。
_SKIP_DIRS = frozenset({
    ".git", ".venv", ".pytest_cache", "__pycache__", "_drafts",
    ".scratch", ".agents", ".bifrost", "build", "dist", "node_modules",
})
_SINGLE_POINT = "core/console.py"
#: 允许清单：路径 → 理由（新增副本必须在这里登记并由 reviewer 判，不能默默加）
_ALLOW: dict[str, str] = {}


def _scan_paths(root: Path = _ROOT) -> list[Path]:
    """扫描面：全仓 `.py`（排除区除外），返回稳定排序的绝对路径。"""
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(
            part in _SKIP_DIRS or part.endswith(".egg-info")
            for part in path.relative_to(root).parts
        )
    )


def _reconfigure_calls(path: Path) -> list[int]:
    """AST 级：只认 `xxx.reconfigure(...)` 调用（注释/字符串里的字样不算）。

    解析失败会抛 ``SyntaxError``/``UnicodeDecodeError``——调用方必须按
    fail-closed 处理，不许当成"没有命中"。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "reconfigure"
    ]


def _hits(root: Path = _ROOT) -> tuple[dict[str, list[int]], dict[str, str]]:
    """→ (命中文件 → 行号, 解析失败文件 → 错误)。"""
    hits: dict[str, list[int]] = {}
    errors: dict[str, str] = {}
    for path in _scan_paths(root):
        rel = path.relative_to(root).as_posix()
        try:
            lines = _reconfigure_calls(path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors[rel] = f"{type(exc).__name__}: {exc}"
            continue
        if lines:
            hits[rel] = lines
    return hits, errors


def test_reconfigure_only_in_single_point():
    """副本不许再长：除单点外任何 `.py` 出现 `reconfigure(` 即红。"""
    hits, errors = _hits()
    assert not errors, (
        "有 .py 无法解析，单点门禁不能证明它没有副本（fail-closed）：\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(errors.items()))
    )
    hits = {k: v for k, v in hits.items() if k not in _ALLOW}
    bad = {k: v for k, v in hits.items() if k != _SINGLE_POINT}
    assert not bad, (
        "控制台自护副本出现在单点之外（应改调用 core/console.py::ensure_utf8_stdio）：\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(bad.items()))
    )


def test_allowlist_entries_still_hit():
    """stale 检测：allowlist 登记的文件必须仍命中（删了/改名了就要清理登记）。"""
    hits, _ = _hits()
    stale = [k for k in _ALLOW if k not in hits]
    assert not stale, f"allowlist 已失效（文件不再命中 reconfigure）：{stale}"


def test_scan_scope_covers_dirs_outside_legacy_list():
    """F5 回归：旧固定清单外的目录（`packaging/`、根级入口）也在扫描面内。

    ⚠ 用**受版本控制**的文件断言（`packaging/build_pipeline.py`）：
    `packaging/entries/` 是 `build_pipeline.py` 生成、被 gitignore 的目录，
    在干净 checkout（CI/新 clone/worktree）里不存在——拿它当锚点会让门禁在
    干净树必红（2026-11-09 发布前复现）。
    """
    scanned = {p.relative_to(_ROOT).as_posix() for p in _scan_paths()}
    assert "main.py" in scanned
    assert "packaging/build_pipeline.py" in scanned


def test_copy_outside_legacy_dirs_is_caught(tmp_path: Path):
    """F5 回归：放在 `packaging/` 下的副本必须被门禁抓到（旧扫描面会漏）。"""
    target = tmp_path / "packaging" / "entries" / "copy.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        'import sys\nsys.stdout.reconfigure(encoding="utf-8")\n', encoding="utf-8"
    )
    hits, errors = _hits(tmp_path)
    assert not errors
    assert "packaging/entries/copy.py" in hits


def test_syntax_error_fails_closed(tmp_path: Path):
    """F5 回归：解析失败的 .py 记入 errors（门禁据此变红），不许静默通过。"""
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    hits, errors = _hits(tmp_path)
    assert not hits
    assert len(errors) == 1 and "SyntaxError" in next(iter(errors.values()))
