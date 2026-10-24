"""check_hardcode.py 自测：引擎约定门禁（规则 1-6）的单元 + 真实仓库回归。

单元用例在 tmp_path 上构造最小语法包（grammar/*/token.toml 的 [id.keyword]）
与引擎文件（core/*.py），验证规则触发/豁免边界；回归用例直接跑真实仓库根，
断言门禁规则（R1/R2/R5）零违规——即"约定即门禁"本身进测试套件。

Doc: tests/policy/test_check_hardcode.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_CHECKER_PATH = Path(__file__).resolve().parent.parent.parent / "policy" / "check_hardcode.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_hardcode", _CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 需模块注册
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()


# 最小 token 协议（R6 从它派生前缀族与协议词汇；真实仓库对应
# core/token_protocol.py，单测树必须自带，否则 R6 无法判定 ⇒ fail-fast）
_MIN_TOKEN_PROTOCOL = '''"""最小 token 协议（单测夹具）：R6 从它派生前缀族与协议词汇。

Doc: core/token_protocol.py
"""

KEYWORD_PREFIX = "keyword."
SYMBOL_PREFIX = "symbol."
BRACKET_L_PREFIX = "bracket.l_"
BRACKET_R_PREFIX = "bracket.r_"
SPACE_PREFIX = "space."
LITERAL_PREFIX = "literal."
MACRO_PREFIX = "macro."
COMMENT_TOKEN_TYPE = "comment"
NEWLINE_TOKEN_TYPE = "newline"
SPACE_FOLD_TOKEN_TYPE = "space.fold"
'''


def _make_tree(tmp_path: Path, engine_code: str, keywords: tuple[str, ...] = ("zzkw",)) -> Path:
    """构造最小扫描树：grammar/v/token.toml + core/a.py + core/token_protocol.py。"""
    grammar = tmp_path / "grammar" / "v"
    grammar.mkdir(parents=True)
    lines = ["[id]", "[id.keyword]"]
    lines += [f'{k} = "{k}"' for k in keywords]
    (grammar / "token.toml").write_text("\n".join(lines), encoding="utf-8")
    core = tmp_path / "core"
    core.mkdir()
    (core / "a.py").write_text(engine_code, encoding="utf-8")
    (core / "token_protocol.py").write_text(_MIN_TOKEN_PROTOCOL, encoding="utf-8")
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


# ── 规则 6：引擎写死具体语言 token 名 ──────────────────────────────────────

def _r6(tmp_path: Path) -> list:
    return checker.collect_findings(tmp_path).results["R6"].violations


def test_rule6_flags_concrete_token_name(tmp_path: Path) -> None:
    """具体 token 名（bracket./symbol. 后代）判红——R1 的词表盲区。"""
    root = _make_tree(tmp_path, 'x = "symbol.base.colon"\n')
    assert [f.line for f in _r6(root)] == [1]


def test_rule6_flags_bracket_name(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = "bracket.l_parentheses"\n')
    assert len(_r6(root)) == 1


def test_rule6_allows_prefix_family(tmp_path: Path) -> None:
    """协议前缀族（`"symbol."` / `"bracket.l_"`）是引擎词汇，不报。"""
    root = _make_tree(tmp_path, 'a = "symbol."\nb = "bracket.l_"\nc = "keyword."\n')
    assert _r6(root) == []


def test_rule6_ignores_comment_and_docstring(tmp_path: Path) -> None:
    """注释/docstring 里讨论 token 名是文档，不是硬编码。"""
    code = '"""说明：symbol.base.colon 这种写法应改声明。"""\n# x = "symbol.base.colon"\ny = 1\n'
    root = _make_tree(tmp_path, code)
    assert _r6(root) == []


def test_rule6_covers_every_protocol_prefix_family(tmp_path: Path) -> None:
    """派生而非枚举：任一协议族（含 literal./space./macro.）的具体名都要被抓。

    回归防"枚举幻觉"：旧实现手写 ("bracket.", "symbol.", "keyword.") 只覆盖
    3/7 个族，`literal.number` 这类具体名整体逃过门禁。
    """
    for lit in ("literal.number", "space.indent", "macro.call", "keyword.module"):
        root = _make_tree(tmp_path / lit.replace(".", "_"), f'x = "{lit}"\n')
        assert len(_r6(root)) == 1, f"{lit} 未被 R6 抓住"


def test_rule6_fails_fast_without_protocol_file(tmp_path: Path) -> None:
    """协议文件缺失 ⇒ 显式报错（不静默降级为"零违规"）。"""
    root = _make_tree(tmp_path, "x = 1\n")
    (root / "core" / "token_protocol.py").unlink()
    with pytest.raises(RuntimeError, match="token_protocol"):
        checker.collect_findings(root)


def test_rule6_is_gate(tmp_path: Path) -> None:
    root = _make_tree(tmp_path, 'x = "keyword.module"\n')
    assert checker.main(["--root", str(root), "--quiet"]) == 1


# ── 真实仓库回归：门禁规则零违规 ──────────────────────────────────

def test_repo_gate_clean() -> None:
    """真实仓库根：R1/R2/R5/R6 必须零违规（约定即门禁进测试套件）。"""
    root = Path(__file__).resolve().parent.parent.parent
    report = checker.collect_findings(root)
    assert report.results["R1"].violations == []
    assert report.results["R2"].violations == []
    assert report.results["R5"].violations == []
    assert report.results["R6"].violations == []
    # 词表来自真实 grammar/（防提取逻辑回归）
    assert "module" in report.vocab
    assert "if" not in report.vocab  # Python 关键字已剔除


def test_rule3_doc_header_beyond_2000_chars(tmp_path: Path) -> None:
    """长 docstring 里合规的 `Doc:` 不得判红（回归：门禁曾只扫前 2000 字符）。

    实测 `core/global_state.py` 的 `Doc:` 在**字符偏移 2597** —— 约定位置是
    "docstring 末行行首"，与"前 2000 字符"无关；门禁须按 docstring 判定，
    否则长 docstring 的文件永久假红。
    """
    filler = "".join(f"说明第 {i} 行，凑长度用。\n" for i in range(200))
    code = f'"""模块说明。\n\n{filler}\nDoc: docs/somewhere.md\n"""\nx = 1\n'
    assert len(code) > 2000, "夹具本身要长过 2000 字符，否则测不到该路径"
    root = _make_tree(tmp_path, code)
    assert checker.collect_findings(root).results["R3"].violations == []
