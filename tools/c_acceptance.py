"""c_acceptance.py — C 包**接受面**扫描（按构造逐条试解析，人工/按需跑，不进日常门禁）。

动机：C 包的"接受面"是它对外的契约（`docs/gaps/gap-language-pack-scope.md`
「C99 接受域清单」），而**空洞是无声的**——构造不被接受时 parser 往往给出**空 AST
而不报错**（语句发现按 FIRST 集挑候选，不属于任何语句入口的构造被整体跳过）。只跑
测试套件看不出"还差哪一族"，逐条试解析才看得见。

用法：
  python tools/c_acceptance.py                      # 默认 grammar/c
  python tools/c_acceptance.py --pack grammar/c --filter 后缀
  python tools/c_acceptance.py --only-gaps          # 只打印不支持项（收尾对照用）

判读：`OK <顶层节点>` = 进 AST；`空 AST` = 该构造整体不被接受（**接受面空洞**）；
`EXC <异常>` = 词法/加载期直接抛错（如预处理指令的 `#`）。

⚠ 用例表是**声明式清单**（与缺口档的接受域清单同源，人工维护）：新增能力后把对应
用例从"不支持"移出并把断言落到 `tests/languages/c/`（本工具只做盘点，不当门禁——
按 `tools/README.md` 纪律，这些工具不进日常门禁）。
Doc: docs/gaps/gap-language-pack-scope.md（C99 接受域清单 / C 包词法面）
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 用例表：(族, 构造说明, 源码) ─────────────────────────────
# 覆盖 C99 的各语法族；命名与缺口档接受域清单一致，便于对照。
# ⚠ **清单会漏项**（2026-11-25 实测）：本表曾漏掉变参 `...`，于是"空洞只剩预处理
#   两项"在工具与文档间互相印证，掩盖了真实缺口。纪律：清单必须与缺口档
#   `docs/gaps/gap-language-pack-scope.md`「C99 接受域清单」**逐行对照**
#   （表里有、清单无 ⇒ 漏项）；新增语言包时同一纪律适用。
CASES: list[tuple[str, str, str]] = [
    ("词法", "整数后缀 U/L/LL", "unsigned long x = 1UL;\n"),
    ("词法", "十六进制 + 后缀", "unsigned int h = 0x1Fu;\n"),
    ("词法", "八进制", "int o = 017;\n"),
    ("词法", "科学计数浮点", "double d = 1.5e-3;\n"),
    ("词法", "浮点后缀", "double f = 1.5f;\n"),
    ("词法", "前导点浮点 `.5`", "double e = .5;\n"),
    ("词法", "字符串内转义引号", 'char *s = "a\\"b";\n'),
    ("声明", "字符字面量与转义", "char c = '\\n';\n"),
    ("声明", "函数指针", "int (*fp)(int);\n"),
    ("声明", "二级指针", "char **argv;\n"),
    ("声明", "多词说明符 + 限定符", "const unsigned long long v = 1ULL;\n"),
    ("声明", "函数说明符 inline", "static inline int g(void) { return 1; }\n"),
    ("声明", "变参 `...`", "int printf(const char *fmt, ...);\n"),
    ("声明", "类型词 _Bool/_Complex", "_Bool b;\nfloat _Complex z;\n"),
    ("声明", "指示符初始化", "int a[4] = {[0] = 1, [3] = 2};\n"),
    ("类型", "struct/union/enum", "struct p { int x; };\nunion u { int i; };\nenum e { A, B, };\n"),
    ("类型", "位域", "struct b { unsigned int f : 3; };\n"),
    ("语句", "控制流全族", "int f(int n) {\n  int i = 0;\n  for (int k = 0; k < n; k++) { i += k; }\n  while (i < n) { i++; }\n  do { i--; } while (i > 0);\n  switch (i) { case 0: break; default: i = 1; }\n  goto done;\ndone:\n  return i;\n}\n"),
    ("表达式", "三目", "int q = a ? b : c;\n"),
    ("表达式", "逗号运算符", "int r = (a, b);\n"),
    ("表达式", "强制转换 (T)x", "int v = (int)x;\n"),
    ("表达式", "sizeof(T)", "unsigned n = sizeof(struct p);\n"),
    ("表达式", "链式成员 a.b.c", "int m = a.b.c;\n"),
    ("表达式", "调用后下标 f(x)[i]", "int n = f(x)[i];\n"),
    ("表达式", "复合字面量", "struct p q = (struct p){1, 2};\n"),
    ("预处理", "#include", "#include <stdio.h>\n"),
    ("预处理", "#define", "#define N 4\n"),
    ("增量", "_Static_assert（c11 插件）", '_Static_assert(1, "x");\n'),
]


def _load(pack: str):
    """加载语言包 → (parser, lexer)。插件目录按约定取 <pack>/plugins。"""
    from core.config_registry import ConfigRegistry
    from core.define import GrammarRulesRegister
    from lexer import Lexer
    from parser import setup_grammar
    from parser.parser_core import Parser
    from parser.rule_selector import RuleSelector

    plugins = os.path.join(pack, "plugins")
    ConfigRegistry.load_language(pack, plugins_dir=plugins)
    rules = setup_grammar(pack, GrammarRulesRegister(), ext_dirs=[plugins])
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=pack, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    return parser, Lexer(rules_dir=pack, ext_dirs=[plugins])


def _try(parser, lexer, src: str) -> tuple[bool, str]:
    """尝试解析 → (是否被接受, 描述)。异常与空 AST 都算"不被接受"。

    解析失败时 parser 会往 stdout/stderr 打 failure-report（几十行）——盘点工具自己
    报告结论即可，故整段重定向掉（同 `tests/e2e/test_real_fidelity.py` 的做法）。
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            ast = parser.parse(lexer.tokenize(src))
    except Exception as exc:  # noqa: BLE001 —— 盘点工具：任何异常都算"该构造不被接受"
        return False, f"EXC {type(exc).__name__}: {str(exc).splitlines()[0][:60]}"
    names = [n.node_name for n in getattr(ast, "sub_node", []) or []]
    return (bool(names), "OK " + ",".join(names) if names else "空 AST")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C 包接受面扫描（逐构造试解析）")
    ap.add_argument("--pack", default="grammar/c", help="语言包目录（默认 grammar/c）")
    ap.add_argument("--filter", default="", help="只看说明含该子串的用例")
    ap.add_argument("--only-gaps", action="store_true", help="只打印不被接受的构造")
    args = ap.parse_args(argv)

    parser, lexer = _load(args.pack)
    ok = gaps = 0
    for family, label, src in CASES:
        if args.filter and args.filter not in label:
            continue
        accepted, desc = _try(parser, lexer, src)
        if accepted:
            ok += 1
        else:
            gaps += 1
        if args.only_gaps and accepted:
            continue
        print(f"[{'接受' if accepted else '空洞'}] {family:4s} {label:22s} {desc}")
    print(f"--- 接受 {ok} / 空洞 {gaps}（共 {ok + gaps} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
