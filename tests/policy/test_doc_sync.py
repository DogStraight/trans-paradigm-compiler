"""doc_sync.py 自测：文档调用点同步层（refs/rename/delete）单元测试。

用例在 tmp_path 上构造最小仓库（docs/ 文件 + 代码 Doc: 头 + 导航索引 +
正文引用），验证：refs 列出全部引用形态、rename 机械替换各形态、
delete 清理机械可清引用、非机械处留人工清单、dry-run 不落盘。

Doc: tests/policy/test_doc_sync.py
"""

import importlib.util
import sys
from pathlib import Path

_SYNC_PATH = Path(__file__).resolve().parent.parent.parent / "policy" / "doc_sync.py"
_GATE_PATH = Path(__file__).resolve().parent.parent.parent / "policy" / "check_doc_refs.py"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# doc_sync import check_doc_refs（同目录）——先把 gate 挂进 sys.modules 再加载
_load("check_doc_refs", _GATE_PATH)
sync = _load("doc_sync", _SYNC_PATH)


def _make_tree(tmp_path: Path, *, docs: dict[str, str] | None = None,
               code: dict[str, str] | None = None,
               nav: dict[str, str] | None = None) -> Path:
    """构造最小仓库：docs/ 文件 + 代码（Doc: 头）+ 导航/正文引用。"""
    for rel, content in (docs or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for rel, content in (code or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for rel, content in (nav or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


# ── refs：列出引用点（全形态）──────────────────────────────────────────────

def test_refs_collects_all_forms(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md\n"""\nx = 1\n'},
        nav={
            "README.md": "[docs/api.md](./docs/api.md)\n",  # 真实 README 形态：文本+URL 都含 docs/
            "docs/README.md": "- 参考：`api.md`\n",
            "AGENTS.md": "调研落 `references.md`\n",
        },
    )
    refs = sync.collect_refs(root, "docs/api.md")
    paths = {(r.path, r.text) for r in refs}
    assert ("core/a.py", "Doc: docs/api.md") in paths  # Doc: 头
    assert ("README.md", "./docs/api.md") in paths  # ./docs/ 链接 URL
    assert ("README.md", "docs/api.md") in paths  # markdown 链接文本
    assert ("docs/README.md", "api.md") in paths  # 裸名
    # AGENTS.md 引用的是 references.md 不是 api.md → 不混入
    assert not any(p == "AGENTS.md" for p, _ in paths)


def test_refs_md_codeblock_excluded(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        nav={"docs/README.md": "```markdown\nDoc: docs/api.md\n```\n"},
    )
    assert sync.collect_refs(root, "docs/api.md") == []


def test_refs_skips_changelog(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        nav={"CHANGELOG.md": "- 见 docs/api.md\n"},
    )
    assert sync.collect_refs(root, "docs/api.md") == []


# ── rename：替换各形态 ─────────────────────────────────────────────────────

def test_rename_updates_doc_header_and_nav(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md\n"""\nx = 1\n'},
        nav={
            "README.md": "[api](./docs/api.md)\n",
            "docs/README.md": "- 参考：`api.md`\n",
        },
    )
    assert sync.cmd_rename(root, "docs/api.md", "docs/ref.md", apply=True) == 0
    assert (root / "docs/ref.md").is_file()
    assert not (root / "docs/api.md").exists()
    assert 'Doc: docs/ref.md\n' in (root / "core/a.py").read_text(encoding="utf-8")
    assert "./docs/ref.md" in (root / "README.md").read_text(encoding="utf-8")
    assert "`ref.md`" in (root / "docs/README.md").read_text(encoding="utf-8")


def test_rename_doc_header_with_trailing_note(tmp_path: Path) -> None:
    # 仓库主流形态（99/114）：`Doc: docs/xxx.md（中文说明）`——只改路径，
    # 保留尾注；且不得产生 `Doc: Doc:` 双前缀
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md（CLI 入口）\n"""\nx = 1\n'},
    )
    assert sync.cmd_rename(root, "docs/api.md", "docs/ref.md", apply=True) == 0
    content = (root / "core/a.py").read_text(encoding="utf-8")
    assert "Doc: docs/ref.md（CLI 入口）" in content
    assert "Doc: Doc:" not in content
    assert "api.md" not in content


def test_rename_dry_run_no_write(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md\n"""\nx = 1\n'},
    )
    assert sync.cmd_rename(root, "docs/api.md", "docs/ref.md", apply=False) == 0
    assert (root / "docs/api.md").is_file()
    assert not (root / "docs/ref.md").exists()
    assert 'Doc: docs/api.md' in (root / "core/a.py").read_text(encoding="utf-8")


def test_rename_subdir_prefix_style(tmp_path: Path) -> None:
    # 子目录文档 + decisions/ 前缀裸引用（MODEL_INDEX 形态）
    root = _make_tree(
        tmp_path,
        docs={"docs/decisions/0001-x.md": "# ADR\n"},
        nav={"docs/MODEL_INDEX.md": "| 条目 | `decisions/0001-x.md` |\n"},
    )
    assert sync.cmd_rename(root, "docs/decisions/0001-x.md",
                           "docs/decisions/0001-y.md", apply=True) == 0
    content = (root / "docs/MODEL_INDEX.md").read_text(encoding="utf-8")
    assert "`decisions/0001-y.md`" in content
    assert "0001-x" not in content


def test_rename_nonexistent_source(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    assert sync.cmd_rename(root, "docs/ghost.md", "docs/x.md", apply=True) == 1


# ── delete：清理机械可清引用 ───────────────────────────────────────────────

def test_delete_removes_doc_and_doc_header(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 弃用\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md\n"""\nx = 1\n'},
    )
    assert sync.cmd_delete(root, "docs/ghost.md", apply=True) == 0
    assert not (root / "docs/ghost.md").exists()
    content = (root / "core/a.py").read_text(encoding="utf-8")
    assert "ghost.md" not in content  # Doc: 头行已删


def test_delete_removes_standalone_nav_line(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 弃用\n"},
        nav={"docs/README.md": "- 参考：`ghost.md`\n- 其它：`api.md`\n",
             "docs/api.md": "# API\n"},
    )
    assert sync.cmd_delete(root, "docs/ghost.md", apply=True) == 0
    content = (root / "docs/README.md").read_text(encoding="utf-8")
    assert "ghost.md" not in content
    assert "api.md" in content  # 其它行保留


def test_delete_inline_ref_needs_manual(tmp_path: Path) -> None:
    # 行内并列引用（同一行还有其它内容）→ 非机械可清 → 拒绝并保留
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 弃用\n"},
        nav={"docs/README.md": "- 参考：`ghost.md` 与 `api.md` 并列\n"},
    )
    assert sync.cmd_delete(root, "docs/ghost.md", apply=True) == 1
    assert (root / "docs/ghost.md").exists()  # 未删除
    content = (root / "docs/README.md").read_text(encoding="utf-8")
    assert "ghost.md" in content  # 引用保留待人工


def test_delete_atomic_no_partial_write(tmp_path: Path) -> None:
    # 原子性：一处引用需人工（行内并列）时，其它可机械清的引用文件
    # 也完全不动——不产生部分提交状态
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 弃用\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md\n"""\nx = 1\n'},
        nav={"docs/README.md": "- 参考：`ghost.md` 与 `api.md` 并列\n"},
    )
    assert sync.cmd_delete(root, "docs/ghost.md", apply=True) == 1
    # core/a.py 的 Doc: 头本可机械删，但原子拒绝 → 未动
    content = (root / "core/a.py").read_text(encoding="utf-8")
    assert "Doc: docs/ghost.md" in content
    assert (root / "docs/ghost.md").exists()


def test_delete_dry_run_no_write(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 弃用\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md\n"""\nx = 1\n'},
    )
    assert sync.cmd_delete(root, "docs/ghost.md", apply=False) == 0
    assert (root / "docs/ghost.md").exists()
    assert 'Doc: docs/ghost.md' in (root / "core/a.py").read_text(encoding="utf-8")


# ── CLI 退出码 ──────────────────────────────────────────────────────────────

def test_main_refs_clean(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, docs={"docs/api.md": "# API\n"})
    assert sync.main(["--root", str(root), "refs", "docs/api.md"]) == 0


def test_main_rename_missing_arg_rejected(tmp_path: Path) -> None:
    # argparse 缺参抛 SystemExit(2)
    import pytest

    root = _make_tree(tmp_path)
    with pytest.raises(SystemExit):
        sync.main(["--root", str(root), "rename", "docs/a.md"])
