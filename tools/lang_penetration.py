"""lang_penetration.py — 语言知识渗透探针（L1 弱信号面）

用途：在引擎目录里找"词法面之外"的渗透**候选**——既有两条门禁抓不到的面：

    `policy/check_hardcode.py`  R1 语言关键字字面量 / R2 grammar 路径 / R3 Doc 头 /
                                R4 引擎 import grammar.<lang> / R5 测试 chdir
    `tools/config_sites.py`     引擎读的配置键是否都在语言包声明（配置面漂移）

本探针补的盲区：

  ① 结构名字面量：引擎字符串里出现**语言包的规则/节点名**（如 "ParamDeclStmt"）
     ——引擎按名认结构 = 知道语言的语法结构，而不是按规则字段/推导。硬信号。
  ② 语义名词标识符：port / width / direction / signal / … 作字段名·参数名·局部名
     ——**弱信号**（普适协议也可能叫这些：linter 的 `width` 是 LSP 诊断列宽、
     `reset_atom_memo` 的 `reset` 是动词）→ 只作人工确认线索，**不能当判据**。
     分两档：Tier A = 语言对象词（优先看）；Tier B = 通用/动作词（仅计数参考）。

判据（L1 三条，见 `TODO.md`「L1」节与 `docs/gaps/gap-language-penetration.md`）：
主判据 = 最小语言包探针（行为面）；辅助 = 声明面缺失探针；本探针 = 弱信号面。
**三条都只覆盖被测路径**，故结论只能是"已知渗透面收敛"，不是"无渗透"。

用法：
    python tools/lang_penetration.py                          # 全引擎目录
    python tools/lang_penetration.py --dirs analyzer linter   # 只看某些子系统
"""
from __future__ import annotations

import ast
import collections
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ("analyzer", "preprocessor", "linter", "parser", "lexer",
                "transform", "renderer", "pipeline", "core")
PACK_GLOB = "grammar/**/*.toml"

# ② 语义名词表（弱信号）。Tier A = 语言对象（强线索，优先看）；
# Tier B = 通用/动作词（弱线索，只计数）。命中不等于渗透，须逐条看调用链。
TIER_A = {
    "port", "ports", "direction", "width", "widths", "bitwidth", "bit_width",
    "signedness", "signal", "signals", "driver", "drivers", "genvar",
    "latch", "hier", "hierarchical", "udp", "typedef", "enum", "interface",
    "concatenation", "inst", "instance", "instances", "clock", "reset",
    "latency", "packed", "unpacked", "replicate", "drives", "fanout",
}
TIER_B = {
    "module", "modules", "param", "parameter", "parameters", "always", "wire",
    "reg", "assign", "load", "loads", "case", "ifdef", "include", "define",
    "macro", "package", "entry", "entries", "signed", "unsigned",
}

_NOUN_SPLIT = re.compile(r"[^a-z0-9]+")


def _engine_files(dirs: tuple[str, ...]) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for d in dirs:
        sub = ROOT / d
        if sub.exists():
            out.extend(sorted(sub.rglob("*.py")))
    return out


def _pack_declared_names() -> set[str]:
    """语言包声明面 → 规则/节点名（TOML 段头里的 PascalCase 名）。"""
    rule_names: set[str] = set()
    for path in sorted(ROOT.glob(PACK_GLOB)):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        rule_names.update(k for k in _walk_keys(data) if re.fullmatch(r"[A-Z][A-Za-z0-9]*", k))
    return rule_names


def _walk_keys(data) -> list[str]:
    """递归收集 TOML 全部键名（段名与字段名一视同仁）。"""
    out: list[str] = []
    for key, value in data.items():
        out.append(key)
        if isinstance(value, dict):
            out.extend(_walk_keys(value))
        elif isinstance(value, list):
            out.extend(k for item in value if isinstance(item, dict) for k in _walk_keys(item))
    return out


def _ident_words(name: str) -> set[str]:
    return {w for w in _NOUN_SPLIT.split(name.lower()) if w}


def _ident_sites(tree: ast.AST) -> list[tuple[int, str]]:
    """所有"标识符位置"的 (行号, 名字)：名字/属性/参数/函数名。"""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            out.append((node.lineno, node.attr))
        elif isinstance(node, ast.Name):
            out.append((node.lineno, node.id))
        elif isinstance(node, ast.arg):
            out.append((node.lineno, node.arg))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.lineno, node.name))
    return out


def main() -> int:
    argv = sys.argv[1:]
    dirs = tuple(argv[argv.index("--dirs") + 1:]) if "--dirs" in argv else DEFAULT_DIRS
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 12

    rule_names = _pack_declared_names()
    structural: list[str] = []
    tier_a: dict[str, list[str]] = collections.defaultdict(list)
    tier_b: collections.Counter[str] = collections.Counter()

    for path in _engine_files(dirs):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in rule_names:
                    structural.append(f'{rel}:{node.lineno}: "{node.value}"')
        for lineno, name in _ident_sites(tree):
            words = _ident_words(name)
            if words & TIER_A:
                tier_a[rel].append(f"{lineno}:{name}")
            if words & TIER_B:
                tier_b[rel.split("/", 1)[0]] += 1

    print(f"语言包声明面：规则/节点名 {len(rule_names)} 个")
    print(f"\n== ① 结构名字面量（硬信号）：{len(structural)} 处")
    for row in structural:
        print("   " + row)

    total_a = sum(len(v) for v in tier_a.values())
    by_dir = collections.Counter(f.split("/", 1)[0] for f in tier_a for _ in tier_a[f])
    print(f"\n== ② Tier A 语言对象词命中：{total_a} 处（"
          + ", ".join(f"{d} {n}" for d, n in by_dir.most_common()) + "）")
    for rel, rows in sorted(tier_a.items(), key=lambda kv: -len(kv[1]))[:top]:
        sample = ", ".join(rows[:6]) + (f" …(+{len(rows) - 6})" if len(rows) > 6 else "")
        print(f"   {len(rows):>4}  {rel}\n          {sample}")
    if len(tier_a) > top:
        print(f"   … 其余 {len(tier_a) - top} 个文件")
    print("\n== ② Tier B 通用/动作词（仅计数参考）："
          + ", ".join(f"{d} {n}" for d, n in tier_b.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
