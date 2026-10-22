"""c_acceptance.py — C 包**接受面**扫描（按构造逐条试解析，人工/按需跑，不进日常门禁）。

动机：C 包的"接受面"是它对外的契约（`docs/gaps/gap-language-pack-scope.md`
「C 语言包：接受域现状」），而**空洞是无声的**——构造不被接受时 parser 往往给出**空 AST
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
Doc: docs/gaps/gap-language-pack-scope.md（C 语言包：接受域现状）
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
#   `docs/gaps/gap-language-pack-scope.md`「C 语言包：接受域现状」**逐行对照**
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
    ("增量", "_Static_assert 文件作用域（c11 插件）", '_Static_assert(1, "x");\n'),
    ("增量", "_Static_assert 块作用域（c11，注入 Stmt 交替）",
     'void f(void) {\n    _Static_assert(1, "x");\n}\n'),
    ("增量", "_Alignof（c11，表达式原子）", "int a = _Alignof(int);\n"),
    ("增量", "_Generic（c11，表达式原子）", "int g = _Generic(x, int: 1, default: 0);\n"),
    ("增量", "_Noreturn / _Thread_local（c11，说明符位）",
     "_Noreturn void die(void);\n_Thread_local int tls;\n"),
    ("增量", "_Alignas（c11，说明符位；常量表达式与类型名两形态）",
     "_Alignas(16) char buf[64];\n_Alignas(double) char c;\n"),
    ("增量", "_Atomic（c11，限定符位 + `_Atomic(T)` 说明符形态）",
     "_Atomic int x;\nint _Atomic y;\n_Atomic(int) z;\n"),
    ("增量", "nullptr / true / false（c23，表达式原子）",
     "int *p = nullptr;\nbool b = true;\n"),
    ("增量", "bool / typeof / constexpr（c23，说明符位）",
     "typeof(int) z;\nconstexpr int n = 4;\n"),
    ("增量", "c23 小写拼写（static_assert 块作用域 / alignas / alignof / thread_local）",
     'void f(void) {\n    static_assert(1, "x");\n}\n'
     "alignas(16) char buf2[64];\nint a2 = alignof(int);\nthread_local int tls;\n"),
    # C23 §6.7.10 消息可省对**两种拼写**都成立（循环 #41）：下划线拼写单参在
    # 文件 / 块两处作用域一并试解析（成员表位在 conformance 测试里）
    ("增量", "c23 单参静态断言下划线拼写（_Static_assert(1)，§6.7.10）",
     "_Static_assert(1);\nvoid f8(void) {\n    _Static_assert(1);\n}\n"),
    ("增量", "c23 类型词（_BitInt(N) / _Decimal32·64·128）",
     "_BitInt(8) a3;\n_Decimal32 d1;\n_Decimal64 d2;\n_Decimal128 d3;\n"),
    ("增量", "c23 属性说明符（[[nodiscard]] / 带前缀 / 多实参 / 尾随逗号 / 属性声明）",
     '[[nodiscard]] int f9(void);\n[[gnu::unused]] int q9;\n'
     '[[gnu::nonnull(1, 2)]] int r9;\n[[nodiscard,]] int s9;\n[[fallthrough]];\n'),
    ("增量", "c23 属性位点：声明符内（标识符之后，§6.7.6）",
     "void f10 [[deprecated]] (void);\nint x10 [[deprecated]] = 1;\n"),
    ("增量", "c23 属性位点：枚举项（`=` 之前，§6.7.2.2）",
     "enum e10 {\n    A10 [[deprecated]] = 1,\n    B10 [[deprecated]]\n};\n"),
    ("增量", "c23 十进制浮点字面量后缀（1.5df / 1.5dd / 1.5dl）",
     "_Decimal32 d4 = 1.5df;\n_Decimal64 d5 = 1.5dd;\n_Decimal128 d6 = 1.5dl;\n"),
    # ⚠ 下面三条是**循环 #37/#38 转正后补进清单的漏项**（原清单当时没加，与缺口档
    #   "清单必须逐行对照"的纪律不符）：字面量前缀族 / 二进制常量 / 数字分隔符。
    ("增量", "字面量前缀族（L / u / U / u8，按档位声明）",
     'char *s11 = L"x";\nchar c11 = u8\'x\';\nchar *s12 = u8"x";\n'),
    ("增量", "c23 二进制常量（0b1010 / 0B1010ULL）",
     "int b11 = 0b1010;\nunsigned b12 = 0B1010ULL;\n"),
    ("增量", "c23 数字分隔符（1'000'000 / 0x1'F / 0b1'0）",
     "int n11 = 1'000'000;\nint n12 = 0x1'F;\nint n13 = 0b1'0;\n"),
    # C23 §6.7.2.2 enum-type-specifier（循环 #42 收口最后一条标准等效缺口）：
    # 带体 / 不透明声明 / 匿名体三种合法形态一并试解析
    ("增量", "c23 枚举固定底层类型（enum e : int，§6.7.2.2）",
     "enum e11 : int { A11 };\nenum e12 : unsigned char;\nenum : int { B11 };\n"),
    # 声明说明符顺序自由 + 指针限定符（循环 #44；C99 §6.7 核心面，真实语料驱动）
    ("声明", "说明符顺序（存储类/限定符 + typedef 名）+ 指针限定符",
     "typedef int T;\nextern T * const p13;\nint f13(const T * const q13);\n"),
    # 无名抽象指针形参（循环 #45；C99 §6.7.6，真实头文件高频：zlib `void zmemcpy(void *, void *, z_size_t);`）
    ("声明", "无名抽象指针形参（原型声明 void f(void *, size_t)）",
     "void f14(void *, size_t);\nint g14(const char *, const char *);\n"),
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


def _preprocess(src: str, pack: str) -> str:
    """预处理器面（与管线同路）：指令消费 + 清理文本。

    直接喂 lexer 会绕过预处理 ⇒ 指令样本（`#define`/`#include`）判不出"指令是否
    被正确消费"。这里走 `scan_directives` 的**真实**路径（与
    `pipeline._stage_macro_scan` 同一入口），返回清理后的文本。
    """
    from preprocessor import scan_directives

    # 返回序见 pipeline/__init__.py::_stage_macro_scan：第 6 项 = 清理后文本
    return scan_directives(src, pack)[5]


def _try(parser, lexer, src: str, pack: str, family: str) -> tuple[bool, str]:
    """尝试解析 → (是否被接受, 描述)。

    路径 = **预处理 → 词法 → 解析**（与管线同路）。接受条件分族：
      · `预处理` 族：**无异常**即可（`#define N 4` 的正确预处理结果就是空翻译
        单元 ⇒ AST 可空；要求非空会把已正确消费的指令误判成空洞）；
      · 其余族：**仍要求 AST 非空**（否则解析失败也会被当成"接受"＝掩盖缺陷）。

    解析失败时 parser 会往 stdout/stderr 打 failure-report（几十行）——盘点工具自己
    报告结论即可，故整段重定向掉（同 `tests/e2e/test_real_fidelity.py` 的做法）。
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            cleaned = _preprocess(src, pack)
            ast = parser.parse(lexer.tokenize(cleaned))
    except Exception as exc:  # noqa: BLE001 —— 盘点工具：任何异常都算"该构造不被接受"
        return False, f"EXC {type(exc).__name__}: {str(exc).splitlines()[0][:60]}"
    names = [n.node_name for n in getattr(ast, "sub_node", []) or []]
    if family == "预处理":
        return True, "OK " + (",".join(names) if names else "空 TU（指令已消费）")
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
        accepted, desc = _try(parser, lexer, src, args.pack, family)
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
