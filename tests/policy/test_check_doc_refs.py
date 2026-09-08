"""check_doc_refs.py 自测：文档调用点门禁（D1-D4）单元 + 真实仓库回归。

单元用例在 tmp_path 上构造最小仓库（docs/ 文件 + 代码 Doc: 头 + 导航
索引），验证规则触发/豁免边界；回归用例直接跑真实仓库根，断言门禁
规则（D1/D2）零违规——"文档调用点防断链"进测试套件。

Doc: tests/policy/test_check_doc_refs.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_CHECKER_PATH = (
    Path(__file__).resolve().parent.parent.parent / "policy" / "check_doc_refs.py"
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_doc_refs", _CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 需模块注册
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()

pytestmark = pytest.mark.smoke  # smoke：policy 组代表（D1-D4 文档门禁，含真仓库回归）


def _make_tree(tmp_path: Path, *, docs: dict[str, str] | None = None,
               code: dict[str, str] | None = None) -> Path:
    """构造最小仓库：docs/ 下 .md + 代码文件（可含 Doc: 头）+ 导航索引。"""
    for rel, content in (docs or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for rel, content in (code or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    # 默认导航：README + docs-README + MODEL_INDEX（空，避免缺文件噪音）
    for nav in ("README.md", "docs/README.md", "docs/MODEL_INDEX.md"):
        p = tmp_path / nav
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
    return tmp_path


def _results(root: Path) -> dict:
    return checker.collect_findings(root).results


# ── D1：代码 Doc: 头目标存在性（gate）──────────────────────────────────────

def test_d1_flags_missing_doc_target(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md\n"""\nx = 1\n'},
    )
    viol = _results(root)["D1"].violations
    assert len(viol) == 1 and "ghost.md" in viol[0].message


def test_d1_doc_header_target_exists(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md\n"""\nx = 1\n'},
    )
    assert _results(root)["D1"].violations == []


def test_d1_non_docs_target_ignored(tmp_path: Path) -> None:
    # Doc: 指向非 docs/ 目标（AGENTS.md / tests README）→ D1 不查
    root = _make_tree(
        tmp_path,
        code={"tools/x.py": '"""模块。\n\nDoc: AGENTS.md\n"""\nx = 1\n'},
    )
    assert _results(root)["D1"].violations == []


def test_d1_subdir_docs_target(tmp_path: Path) -> None:
    # decisions/ 子路径的 Doc: 引用也应解析
    root = _make_tree(
        tmp_path,
        docs={"docs/decisions/0001-x.md": "# ADR\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/decisions/0001-x.md\n"""\nx = 1\n'},
    )
    assert _results(root)["D1"].violations == []


def test_d1_doc_header_with_trailing_note(tmp_path: Path) -> None:
    # 带中文尾注的 Doc: 头（仓库主流形态）目标缺失也要报
    root = _make_tree(
        tmp_path,
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md（CLI 入口）\n"""\nx = 1\n'},
    )
    viol = _results(root)["D1"].violations
    assert len(viol) == 1 and "ghost.md" in viol[0].message


def test_d1_doc_header_with_trailing_note_exists(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md（CLI 入口）\n"""\nx = 1\n'},
    )
    assert _results(root)["D1"].violations == []


# ── D2：导航索引条目存在性（gate）──────────────────────────────────────────

def test_d2_flags_missing_nav_entry(tmp_path: Path) -> None:
    root = _make_tree(tmp_path)
    (tmp_path / "docs/README.md").write_text(
        "- 参考：`ghost_doc.md`\n", encoding="utf-8"
    )
    viol = _results(root)["D2"].violations
    assert len(viol) == 1 and "ghost_doc.md" in viol[0].message


def test_d2_link_form_and_bare_form(tmp_path: Path) -> None:
    # README 用 ./docs/ 链接形态；docs-README 用裸文件名形态
    root = _make_tree(tmp_path, docs={"docs/api.md": "# API\n"})
    (tmp_path / "README.md").write_text(
        "[api](./docs/api.md)\n", encoding="utf-8"
    )
    (tmp_path / "docs/README.md").write_text(
        "- 参考：`api.md`\n", encoding="utf-8"
    )
    assert _results(root)["D2"].violations == []


def test_d2_non_docs_bare_name_ignored(tmp_path: Path) -> None:
    # docs-README 里裸名 AGENTS.md（仓库根存在）→ 非 docs 引用不报
    root = _make_tree(tmp_path, docs={"docs/api.md": "# API\n"})
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (tmp_path / "docs/README.md").write_text(
        "- 约定：`AGENTS.md`\n- 参考：`api.md`\n", encoding="utf-8"
    )
    assert _results(root)["D2"].violations == []


def test_d2_nav_codeblock_excluded(tmp_path: Path) -> None:
    # 导航里的 ``` 代码块示例不是真实索引条目（docs/README 格式示范形态）
    root = _make_tree(tmp_path, docs={"docs/api.md": "# API\n"})
    (tmp_path / "docs/README.md").write_text(
        "## 示例\n\n```markdown\nDoc: docs/ghost_example.md\n```\n",
        encoding="utf-8",
    )
    assert _results(root)["D2"].violations == []


# ── D3：Impl:/Test: 文件级存在（info）──────────────────────────────────────

def test_d3_flags_missing_impl_file(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "> Impl: core/nope.py::fn\n"},
        code={"core/a.py": "x = 1\n"},
    )
    viol = _results(root)["D3"].violations
    assert len(viol) == 1 and "nope.py" in viol[0].message


def test_d3_existing_impl_file_ok(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "> Impl: core/a.py::fn\n"},
        code={"core/a.py": "def fn(): pass\n"},
    )
    assert _results(root)["D3"].violations == []


def test_d3_bare_filename_inherits_dir(tmp_path: Path) -> None:
    # `tests/a.py / b.py` → b.py 继承 tests/ 目录
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "> Test: tests/a.py / b.py\n"},
        code={"tests/a.py": "x = 1\n", "tests/b.py": "x = 1\n"},
    )
    assert _results(root)["D3"].violations == []


def test_d3_codeblock_excluded(tmp_path: Path) -> None:
    # 文档内 ``` 代码块里的 Impl: 行是示意，不是真实引用
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "```markdown\n> Impl: core/ghost.py::x\n```\n"},
        code={"core/a.py": "x = 1\n"},
    )
    assert _results(root)["D3"].violations == []


def test_d3_glob_form_nonempty_ok(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "> Impl: grammar/**/*.toml\n"},
    )
    assert _results(root)["D3"].violations == []


# ── D4：孤儿文档（info）────────────────────────────────────────────────────

def test_d4_flags_orphan_doc(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        docs={"docs/ghost.md": "# 无引用文档\n"},
    )
    viol = _results(root)["D4"].violations
    assert any("ghost.md" in f.path for f in viol)


def test_d4_referenced_doc_ok(tmp_path: Path) -> None:
    # 被代码 Doc: 引用 → 非孤儿
    root = _make_tree(
        tmp_path,
        docs={"docs/api.md": "# API\n"},
        code={"core/a.py": '"""模块。\n\nDoc: docs/api.md\n"""\nx = 1\n'},
    )
    assert _results(root)["D4"].violations == []


def test_d4_nav_files_exempt(tmp_path: Path) -> None:
    # docs/README、MODEL_INDEX 自身是导航，不算孤儿
    root = _make_tree(tmp_path)
    viol_paths = [f.path for f in _results(root)["D4"].violations]
    assert "docs/README.md" not in viol_paths
    assert "docs/MODEL_INDEX.md" not in viol_paths


# ── CLI 退出码 ──────────────────────────────────────────────────────────────

def test_main_exit_code_clean(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, docs={"docs/api.md": "# API\n"})
    assert checker.main(["--root", str(root), "--quiet"]) == 0


def test_main_exit_code_violation(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path,
        code={"core/a.py": '"""模块。\n\nDoc: docs/ghost.md\n"""\nx = 1\n'},
    )
    assert checker.main(["--root", str(root), "--quiet"]) == 1


def test_main_d3_info_not_gate(tmp_path: Path) -> None:
    # D3 是 info：仅 D3 违规不改变退出码
    root = _make_tree(
        tmp_path,
        docs={"docs/arch.md": "> Impl: core/nope.py::fn\n"},
        code={"core/a.py": "x = 1\n"},
    )
    assert checker.main(["--root", str(root), "--quiet"]) == 0


# ── 真实仓库回归：门禁规则零违规 ────────────────────────────────────────────

def test_repo_gate_clean() -> None:
    """真实仓库根：D1/D2 必须零违规（文档调用点防断链进测试套件）。"""
    root = Path(__file__).resolve().parent.parent.parent
    results = checker.collect_findings(root).results
    assert results["D1"].violations == []
    assert results["D2"].violations == []
