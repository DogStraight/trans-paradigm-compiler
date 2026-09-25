"""check_hardcode.py — 引擎约定机器化检查器（AGENTS.md 硬约束 → 自动门禁）。

把 AGENTS.md 的"语言知识不进代码 / 路径规范 / Doc 反向引用"从文档约定
变成可执行检查（纯 Python 零依赖，挂 CI）：

  规则 1 [gate]  语言 token 不得以字符串字面量出现在引擎代码
                （词表从 grammar/ 实际 [id.keyword] 提取，防硬编码词表漂移）
  规则 2 [gate]  不得硬编码 grammar/<lang> 相对路径字面量（P2.4 路径问题防复发）
  规则 3 [info]  文件头 Doc: 反向引用缺失（--strict-doc 升为 gate）
  规则 4 [info]  引擎代码不得直接 import grammar.<lang> 插件（--strict-import 升为 gate）
  规则 5 [gate]  测试文件不得直接 os.chdir（进程级 CWD 泄漏 → 并行 worker
                相互踩相对路径；需要时用 monkeypatch.chdir）

扫描范围：引擎目录（core/lexer/parser/linter/preprocessor/analyzer/transform/
renderer/pipeline）+ main.py；grammar/ 下的语言插件代码（plugins/*.py）是
语言侧代码，允许含语言知识，不在扫描范围。

用法：
  python policy/check_hardcode.py             # 门禁规则 1/2
  python policy/check_hardcode.py --strict-doc --strict-import
  python policy/check_hardcode.py --root <dir>   # 指定扫描根（测试用）

退出码：0 = 门禁规则全干净；1 = 存在门禁违规（规则 1/2 或 strict 升格的规则）。

Doc: AGENTS.md
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

# ── 扫描范围 ────────────────────────────────────────────────────────────────
# 引擎目录（通用骨架，语言知识禁止进入）；grammar/ 下语言插件代码不在范围。
ENGINE_DIRS: tuple[str, ...] = (
    "core",
    "lexer",
    "parser",
    "linter",
    "preprocessor",
    "analyzer",
    "transform",
    "renderer",
    "pipeline",
)
EXTRA_FILES: tuple[str, ...] = ("main.py",)

# 实现语言关键字：词表提取后剔除，避免 Python 自身关键字误报
# （如 verilog 的 if/else/while 与 c4 的 return 与 Python 同名）。
PY_KEYWORDS: frozenset[str] = frozenset(
    {
        "False", "None", "True", "and", "as", "assert", "async", "await",
        "break", "class", "continue", "def", "del", "elif", "else", "except",
        "finally", "for", "from", "global", "if", "import", "in", "is",
        "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
        "while", "with", "yield",
    }
)

# 规则 1 allowlist：与引擎协议词表同名的 grammar 关键字（引擎自身词汇，
# 非语言知识），逐项注明原因。新增冲突词须评审后加入。
TOKEN_ALLOWLIST: dict[str, str] = {
    "type": "规则字段/通用词（parser/transform/analyzer 配置协议）",
    "repeat": "规则形态字段（repeat/plus/optional 规则类型）",
    "join": "renderer 原语注册键（引擎 DSL 词表，与 sim 插件关键字同名）",
    "end": "LSP 诊断范围字段 range.end",
    "default": "配置字段默认值（config/default 语义）",
    "input": "管线阶段字段（输入文件名 ctx.base_name）",
    "output": "管线结果字段（ctx.result['output']）",
    "signed": "number 配置字段（cfg.get('signed')，[number] 数字词法配置）",
    "config": "CLI 子命令名（tpc config dump/show——工程命令，与 configs 插件关键字同名）",
    "table": "transform 映射表键名（mapping table 的 'table' 字段，与 udp 插件关键字同名）",
    "include": "preprocessor 指令配置键名（_directives_cfg['include']，宏/包含指令配置协议，与 configs 插件 library 的 include 语句同名）",
    "impl": "加工单元配置字段（[pipeline.units.<name>].impl，ADR-0015 §1 显式配置品类）",
    "fn": "postpass 声明解析出的函数引用键（[[analyzer.postpasses]].run → decl['fn']，引擎内部键名）",
    # C 包（grammar/c）关键字与引擎协议词同名——均为引擎自身词汇，非语言知识。
    # 加 C 包后本门禁第一次跑到这些冲突（verilog/c4 的关键字不撞这几个词）。
    "inline": "规则形态字段（[Rule.parser] inline = true）+ renderer 槽名（slots['inline']），与 C 关键字同名",
    "register": "全局态注册面字段名（GrammarRulesRegister 的 '_default_instance'/'register'），与 C 存储类关键字同名",
    "auto": "lexer 缩进配置值（indent level == 'auto'），与 C 存储类关键字同名",
    "switch": "transform 统计键名（engine._stats['switch']），与 C 语句关键字同名",
    # C23 档（plugins/c23）引入的关键字与引擎词汇撞名——`bool` 是引擎的 token 类别谓词名
    # （parser/pratt_parser.py::is_bool 里的 `_check("bool", token)`，指引擎 token 类别，
    # 不是 C 的 `bool` 类型）。同上：引擎自身词汇，非语言知识。
    "bool": "token 类别谓词名（pratt_parser 的 is_bool/_check('bool', …)），与 C23 关键字同名",
}

# 规则 2 allowlist：文档化的默认语言引导路径（产品决策：verilog 为默认
# 语言包，用户配置缺失时回退；editable/wheel 双模式定位，两处均有注释）。
PATH_ALLOWLIST: dict[str, str] = {
    "grammar/verilog": "默认语言包引导路径（define.py/config_registry.py 回退默认）",
}

# 字符串字面量正则已弃用（改为 tokenize 提取）；仅保留路径形态判定
_PATH_LITERAL_RE = re.compile(r"^grammar[/\\][A-Za-z0-9_]+(?=[/\\]|$)")

# 文件头 Doc: 反向引用（docs/README.md 约定：文件头 docstring 末行）
_DOC_RE = re.compile(r"^Doc:\s*\S+", re.MULTILINE)

# 规则 4：引擎代码直接导入 grammar.<lang> 包
_GRAMMAR_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+grammar\.[A-Za-z0-9_]+")

# 规则 5：测试文件（test_*.py / conftest.py）范围与禁止的 CWD 切换
_TEST_FILE_RE = re.compile(r"^tests/(?:.+/)?(?:test_[^/]*\.py|conftest\.py)$")


@dataclass(frozen=True)
class Finding:
    """一条检查发现。"""

    rule: str
    path: str
    line: int
    message: str
    detail: str = ""


@dataclass
class RuleResult:
    """单条规则的检查结果。"""

    violations: list[Finding]
    skipped: list[Finding]


@dataclass
class CheckReport:
    """全量检查报告。"""

    vocab: set[str]
    results: dict[str, RuleResult]


# ── 词表与文件收集 ──────────────────────────────────────────────────────────

def collect_grammar_keywords(root: Path) -> set[str]:
    """从 grammar/ 全部 TOML 的 [id.keyword] 提取语言关键字（防词表漂移）。

    遍历所有语言包与插件（union），因为引擎可能加载任意语言——代码对
    任何语言的 token 都不得硬编码。返回剔除 Python 关键字后的词表。
    """
    vocab: set[str] = set()
    grammar_dir = root / "grammar"
    if not grammar_dir.is_dir():
        return vocab
    for toml_path in grammar_dir.rglob("*.toml"):
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError):
            continue
        id_cfg = data.get("id") or {}
        for value in (id_cfg.get("keyword") or {}).values():
            if isinstance(value, str):
                vocab.add(value)
    return vocab - PY_KEYWORDS


def _iter_engine_files(root: Path) -> Iterator[Path]:
    """产出引擎目录 + main.py 下的全部 .py 文件（相对 root）。"""
    for name in ENGINE_DIRS:
        base = root / name
        if base.is_dir():
            for path in sorted(base.rglob("*.py")):
                yield path.relative_to(root)
    for name in EXTRA_FILES:
        path = root / name
        if path.is_file():
            yield Path(name)


def _iter_test_files(root: Path) -> Iterator[Path]:
    """产出测试文件（tests/**/test_*.py 与 conftest.py，相对 root）。

    不含 tests/e2e/eval_*.py 等手动脚本：它们以 `main()` 内 `os.chdir(_ROOT)`
    定位相对路径，是单进程一次性运行的工具，不参与并行测试进程共享 CWD。
    """
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return
    for path in sorted(tests_dir.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if _TEST_FILE_RE.match(rel):
            yield Path(rel)


def _iter_code_literals(text: str) -> Iterator[tuple[int, str]]:
    """逐行产出代码中的字符串字面量内容（tokenize 精确区分代码/注释/docstring）。

    用标准库 tokenize 取 STRING token：
    - COMMENT token（注释）天然排除——注释里讨论语法示例是文档不是硬编码；
    - 三引号 docstring（单行/多行）排除——docstring 里的示例（如
      ``如 "grammar/c4"``）是文档；
    - f-string 等非常量字面量跳过（ast.literal_eval 失败）。
    """
    text = text.lstrip("\ufeff")
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return
    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        if tok.string.startswith(('"""', "'''")):
            continue  # docstring（单行/多行均排除）
        try:
            value = ast.literal_eval(tok.string)
        except (ValueError, SyntaxError):
            continue  # f-string 等非常量字面量
        if isinstance(value, str):
            yield tok.start[0], value


# ── 规则实现 ────────────────────────────────────────────────────────────────

def _rule1_token_literals(root: Path, vocab: set[str]) -> tuple[list[Finding], list[Finding]]:
    """规则 1：语言 token 字符串字面量。返回 (违规, allowlist 跳过)。"""
    violations: list[Finding] = []
    skipped: list[Finding] = []
    for rel in _iter_engine_files(root):
        text = (root / rel).read_text(encoding="utf-8")
        for line_no, lit in _iter_code_literals(text):
            if lit not in vocab:
                continue
            if lit in TOKEN_ALLOWLIST:
                skipped.append(
                    Finding("R1", str(rel), line_no, f"token '{lit}'", TOKEN_ALLOWLIST[lit])
                )
            else:
                violations.append(
                    Finding("R1", str(rel), line_no, f"语言 token 字符串字面量 '{lit}'")
                )
    return violations, skipped


def _rule2_grammar_paths(root: Path) -> tuple[list[Finding], list[Finding]]:
    """规则 2：grammar/<lang> 相对路径字面量。返回 (违规, allowlist 跳过)。"""
    violations: list[Finding] = []
    skipped: list[Finding] = []
    for rel in _iter_engine_files(root):
        text = (root / rel).read_text(encoding="utf-8")
        for line_no, lit in _iter_code_literals(text):
            if not _PATH_LITERAL_RE.match(lit):
                continue
            if lit in PATH_ALLOWLIST:
                skipped.append(
                    Finding("R2", str(rel), line_no, f"路径 '{lit}'", PATH_ALLOWLIST[lit])
                )
            else:
                violations.append(
                    Finding("R2", str(rel), line_no, f"grammar 相对路径字面量 '{lit}'")
                )
    return violations, skipped


def _rule3_doc_headers(root: Path) -> list[Finding]:
    """规则 3（info）：文件头 Doc: 反向引用缺失。"""
    findings: list[Finding] = []
    for rel in _iter_engine_files(root):
        head = (root / rel).read_text(encoding="utf-8")[:2000]
        if not _DOC_RE.search(head):
            findings.append(Finding("R3", str(rel), 1, "文件头缺 Doc: 反向引用"))
    return findings


def _rule4_grammar_imports(root: Path) -> list[Finding]:
    """规则 4（info）：引擎代码直接 import grammar.<lang> 插件。"""
    findings: list[Finding] = []
    for rel in _iter_engine_files(root):
        for line_no, line in enumerate(
            (root / rel).read_text(encoding="utf-8").splitlines(), 1
        ):
            if _GRAMMAR_IMPORT_RE.match(line):
                findings.append(
                    Finding("R4", str(rel), line_no, "直接导入 grammar.<lang> 插件", line.strip())
                )
    return findings


def _rule5_no_chdir_in_tests(root: Path) -> list[Finding]:
    """规则 5：测试文件直接 `os.chdir`（进程级 CWD 泄漏）。

    xdist worker 共享进程 CWD：一个测试切了不还原，同 worker 后续测试的
    相对路径（`grammar/verilog`、`tests/e2e/samples/...`）全部落在错位置
    ——与全局态泄漏同类，但现象更隐蔽（文件找不到/读到别的文件）。用
    `monkeypatch.chdir`（自动还原）或绝对路径。
    """
    findings: list[Finding] = []
    for rel in _iter_test_files(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "chdir"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                findings.append(
                    Finding(
                        "R5",
                        str(rel),
                        node.lineno,
                        "测试内直接 os.chdir（改用 monkeypatch.chdir）",
                    )
                )
    return findings


# ── 汇总与 CLI ──────────────────────────────────────────────────────────────

def collect_findings(root: Path) -> CheckReport:
    """跑全部规则，返回 CheckReport（测试与 CLI 共用入口）。"""
    vocab = collect_grammar_keywords(root)
    r1_viol, r1_skip = _rule1_token_literals(root, vocab)
    r2_viol, r2_skip = _rule2_grammar_paths(root)
    return CheckReport(
        vocab=vocab,
        results={
            "R1": RuleResult(r1_viol, r1_skip),
            "R2": RuleResult(r2_viol, r2_skip),
            "R3": RuleResult(_rule3_doc_headers(root), []),
            "R4": RuleResult(_rule4_grammar_imports(root), []),
            "R5": RuleResult(_rule5_no_chdir_in_tests(root), []),
        },
    )


def _print_findings(title: str, findings: Sequence[Finding]) -> None:
    if not findings:
        print(f"  {title}: 0")
        return
    print(f"  {title}: {len(findings)}")
    for f in findings:
        loc = f"{f.path}:{f.line}"
        suffix = f" — {f.detail}" if f.detail else ""
        print(f"      {loc}: {f.message}{suffix}")


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 参数面（prog / 描述 / 四个开关）。"""
    parser = argparse.ArgumentParser(
        prog="check_hardcode",
        description="引擎约定门禁：语言知识不进代码（AGENTS.md 硬约束机器化）",
    )
    parser.add_argument("--root", default=None, help="扫描根目录（默认仓库根；测试/诊断用）")
    parser.add_argument("--strict-doc", action="store_true", help="规则 3 升为 gate")
    parser.add_argument("--strict-import", action="store_true", help="规则 4 升为 gate")
    parser.add_argument("--quiet", action="store_true", help="只输出违规与结论")
    return parser


def _gate_rule_ids(args: argparse.Namespace) -> set[str]:
    """gate 规则集：R1/R2/R5 常驻，R3/R4 由 --strict-* 升格。"""
    gate: set[str] = {"R1", "R2", "R5"}
    if args.strict_doc:
        gate.add("R3")
    if args.strict_import:
        gate.add("R4")
    return gate


def _rule_label(rule_id: str, gate: set[str]) -> str:
    """规则分级标签（gate / gate（--strict 升格）/ info）。"""
    if rule_id not in gate:
        return "info"
    return "gate（--strict 升格）" if rule_id in ("R3", "R4") else "gate"


def _print_rule_reports(report: CheckReport, gate: set[str], quiet: bool) -> None:
    """逐规则打印：分级标签 + 违规 + allowlist 跳过（quiet 省表头与跳过项）。"""
    if not quiet:
        print(
            f"[tpc 约定门禁] 词表 {len(report.vocab)} 个关键字"
            "（grammar/ 提取，剔除 Python 关键字）"
        )
    for rule_id in ("R1", "R2", "R3", "R4", "R5"):
        res = report.results[rule_id]
        if not quiet:
            print(f"── 规则 {rule_id} [{_rule_label(rule_id, gate)}]")
        _print_findings(f"{rule_id} 发现", res.violations)
        if res.skipped and not quiet:
            _print_findings(f"{rule_id} allowlist 跳过", res.skipped)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    report = collect_findings(root)
    gate = _gate_rule_ids(args)

    _print_rule_reports(report, gate, args.quiet)

    gate_findings = sum(len(report.results[r].violations) for r in gate)
    if gate_findings:
        print(f"[FAIL] 门禁违规 {gate_findings} 处（{', '.join(sorted(gate))}）")
        return 1
    print("[PASS] 引擎约定门禁全干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
