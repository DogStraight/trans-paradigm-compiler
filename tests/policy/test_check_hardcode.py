"""check_hardcode.py 自测：引擎约定门禁（规则 1-5）的单元 + 真实仓库回归。

单元用例在 tmp_path 上构造最小语法包（grammar/*/token.toml 的 [id.keyword]）
与引擎文件（core/*.py），验证规则触发/豁免边界；回归用例直接跑真实仓库根，
断言门禁规则（R1/R2/R5）零违规——即"约定即门禁"本身进测试套件。

Doc: tests/policy/test_check_hardcode.py
"""

import importlib.util
import sys
from pathlib import Path

_CHECKER_PATH = Path(__file__).resolve().parent.parent.parent / "policy" / "check_hardcode.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_hardcode", _CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 需模块注册
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()


def _make_tree(tmp_path: Path, engine_code: str, keywords: tuple[str, ...] = ("zzkw",)) -> Path:
    """构造最小扫描树：grammar/v/token.toml（[id.keyword]）+ core/a.py。"""
    grammar = tmp_path / "grammar" / "v"
    grammar.mkdir(parents=True)
    lines = ["[id]", "[id.keyword]"]
    lines += [f'{k} = "{k}"' for k in keywords]
    (grammar / "token.toml").write_text("\n".join(lines), encoding="utf-8")
    core = tmp_path / "core"
    core.mkdir()
    (core / "a.py").write_text(engine_code, encoding="utf-8")
    return tmp_path


def _r1(tmp_path: Path) -> list:
    return checker.collect_findings(tmp_path).results["R1"].violations


# ── 规则 1：语言 token 字符串字面量 ────────────────────────────────────────

def test_rule1_flags_keyword_literal(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = "zzkw"\n')
    assert [f.line for f in _r1(root)] == [1]


def test_rule1_python_keyword_excluded(tmp_path: Path) -> None:
    # "for" 同时是 verilog/c4 关键字与 Python 关键字 → 词表剔除，不误报
    root = _make_tree(tmp_path, 'x = "for"\n', keywords=("for", "zzkw"))
    assert _r1(root) == []


def test_rule1_allowlist_not_flagged(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = "join"\n', keywords=("join",))
    assert _r1(root) == []


def test_rule1_comment_and_docstring_excluded(tmp_path: Path) -> None:
    code = (
        '# 注释示例 "zzkw" 是文档\n'
        '"""单行 docstring "zzkw" 示例"""\n'
        '"""多行 docstring：\n'
        '    "zzkw" 也是文档\n'
        '"""\n'
        "x = 1\n"
    )
    root = _make_tree(tmp_path, code)
    assert _r1(root) == []


def test_rule1_fstring_not_flagged(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = f"{y}"\n')
    assert _r1(root) == []


def test_rule1_word_boundary(tmp_path: Path) -> None:
    # 完整字面量才匹配："zzkw" 与 "zzkw_x" 是不同字面量，后者不是 token
    root = _make_tree(tmp_path, 'x = "zzkw_x"\n')
    assert _r1(root) == []


# ── 规则 2：grammar 相对路径字面量 ─────────────────────────────────────────

def _r2(tmp_path: Path):
    results = checker.collect_findings(tmp_path).results["R2"]
    return results.violations, results.skipped


def test_rule2_flags_lang_relative_path(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'p = "grammar/c4/tpc.toml"\n')
    viol, _ = _r2(root)
    assert [f.line for f in viol] == [1]


def test_rule2_config_file_reference_ok(tmp_path: Path) -> None:
    # "grammar/tpc.toml"（无语言目录）是配置文件引用，不算语言路径
    root = _make_tree(tmp_path, 'p = "grammar/tpc.toml"\n')
    viol, _ = _r2(root)
    assert viol == []


def test_rule2_bootstrap_default_allowlisted(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'grammar_dir = "grammar/verilog"\n')
    viol, skipped = _r2(root)
    assert viol == []
    assert [f.detail for f in skipped if "grammar/verilog" in f.message]


# ── 规则 3：文件头 Doc: 反向引用（info） ───────────────────────────────────

def test_rule3_missing_doc_header(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = 1\n")
    assert len(checker.collect_findings(root).results["R3"].violations) == 1


def test_rule3_with_doc_header(tmp_path: Path) -> None:
    # docs/README.md 约定形态：docstring 末行行首声明 Doc:
    code = '"""模块说明。\n\nDoc: docs/somewhere.md\n"""\nx = 1\n'
    root = _make_tree(tmp_path, code)
    assert checker.collect_findings(root).results["R3"].violations == []


# ── 规则 4：直接导入 grammar.<lang> 插件（info） ───────────────────────────

def test_rule4_flags_grammar_import(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "from grammar.verilog.plugins.formatter import build_engine\n")
    assert len(checker.collect_findings(root).results["R4"].violations) == 1


def test_rule4_variable_attr_not_flagged(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = grammar.get('files')\n")
    assert checker.collect_findings(root).results["R4"].violations == []


# ── 规则 5：测试文件禁 os.chdir（gate） ────────────────────────────

def _add_test_file(root: Path, rel: str, code: str) -> Path:
    """在扫描树里放一个测试文件（rel 为 tests/ 下相对路径）。"""
    path = root / "tests" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return path


def _r5(tmp_path: Path) -> list:
    return checker.collect_findings(tmp_path).results["R5"].violations


def test_rule5_flags_os_chdir_in_test(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = 1\n")
    _add_test_file(root, "unit/test_a.py", "import os\nos.chdir('/tmp')\n")
    assert [f.line for f in _r5(root)] == [2]


def test_rule5_monkeypatch_chdir_ok(tmp_path: Path) -> None:
    """monkeypatch.chdir 自动还原，是推荐做法，不报。"""
    root = _make_tree(tmp_path, "x = 1\n")
    _add_test_file(
        root, "unit/test_a.py", "def test_x(tmp_path, monkeypatch):\n    monkeypatch.chdir(tmp_path)\n"
    )
    assert _r5(root) == []


def test_rule5_engine_and_scripts_out_of_scope(tmp_path: Path) -> None:
    """引擎代码与手动脚本（eval_*.py）不属规则 5 范围。"""
    root = _make_tree(tmp_path, "import os\nos.chdir('.')\n")
    _add_test_file(root, "e2e/eval_benchmark.py", "import os\nos.chdir('.')\n")
    assert _r5(root) == []


# ── CLI 退出码 ──────────────────────────────────────────────────────────────

def test_main_exit_code_clean(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = 1\n")
    assert checker.main(["--root", str(root), "--quiet"]) == 0


def test_main_exit_code_violation(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = "zzkw"\n')
    assert checker.main(["--root", str(root), "--quiet"]) == 1


def test_main_strict_doc_escalates(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = 1\n")  # 无 Doc: 头 → R3 违规
    assert checker.main(["--root", str(root), "--quiet", "--strict-doc"]) == 1


def test_main_r5_is_gate(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, "x = 1\n")
    _add_test_file(root, "unit/test_a.py", "import os\nos.chdir('.')\n")
    assert checker.main(["--root", str(root), "--quiet"]) == 1


# ── 真实仓库回归：门禁规则零违规 ──────────────────────────────────

def test_repo_gate_clean() -> None:
    """真实仓库根：R1/R2/R5 必须零违规（约定即门禁进测试套件）。"""
    root = Path(__file__).resolve().parent.parent.parent
    report = checker.collect_findings(root)
    assert report.results["R1"].violations == []
    assert report.results["R2"].violations == []
    assert report.results["R5"].violations == []
    # 词表来自真实 grammar/（防提取逻辑回归）
    assert "module" in report.vocab
    assert "if" not in report.vocab  # Python 关键字已剔除
