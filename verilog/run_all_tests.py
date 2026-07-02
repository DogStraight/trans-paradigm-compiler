#!/usr/bin/env python3
"""End-to-end regression test — 与 run_pipeline.py 共享同套测试发现逻辑。

用法:
    python run_all_tests.py                    # 所有测试
    python run_all_tests.py normal             # normal 组
    python run_all_tests.py errors             # errors 组
    python run_all_tests.py normal counter     # normal/ref_counter
    python run_all_tests.py -v                 # 详细输出
    python run_all_tests.py --json             # JSON 报告
"""

import sys, os, json, time

sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lexer import Lexer
from parser import Parser, setup_grammar
from core.define import ParseError, FileManager
from parser.rule_selector import RuleSelector as _RS, set_default_cache_path
from transform.pre.normalizer import normalize_ast
from analyzer import SemanticAnalyzer
from transform.post import AstTransformer
from transform.post.engine import ConfigDrivenTransform
from renderer.renderer import Renderer

RULES_DIR = os.path.join(project_root, "grammar", "rules_verilog")
EXT_DIR = os.path.join(project_root, "grammar", "rules_verilog_ext")


def run_all(
    verbose=False,
    json_out=False,
    inline_comments=False,
    expand_macros=False,
    group_filter=None,
    name_filter=None,
):
    # Setup start token cache
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(base_dir, ".cache", "start_tokens.json")
    set_default_cache_path(cache_path)

    # Load grammar
    rules = setup_grammar(RULES_DIR, EXT_DIR)

    # Initialize parser
    parser = Parser(rules_dir=RULES_DIR, cache_enabled=False)
    parser.grammar_rules = rules
    parser.statement_rule_names = [
        name
        for name, rule in rules.items()
        if hasattr(rule, "has_pass_end_case")
        and rule.has_pass_end_case()
        and name != "Expression"
    ]
    parser.rule_selector = _RS(rules, parser.statement_rule_names)
    parser.atomic_rules = sorted(
        (rule for rule in rules.values() if getattr(rule, "atomic", False)),
        key=lambda r: len(getattr(r, "production", [])),
        reverse=True,
    )

    lex = Lexer(rules_dir=RULES_DIR)
    renderer = Renderer(RULES_DIR)
    analyzer = SemanticAnalyzer(rules)
    transformer = AstTransformer()
    transformer.register(
        ConfigDrivenTransform(
            rules=rules,
            ext_dir=FileManager.get_full_path(EXT_DIR),
        )
    )

    # 收集测试用例 — 与 run_pipeline.py 相同的双目录发现
    tests_dir = os.path.join(base_dir, "tests")
    cases: list[tuple[str, str, str]] = []  # (name, path, group)
    groups = [group_filter] if group_filter else ["normal", "errors"]
    for group in groups:
        group_ref = os.path.join(tests_dir, group, "ref")
        if not os.path.isdir(group_ref):
            continue
        for f in os.listdir(group_ref):
            if not f.endswith(".v") or f.startswith("_"):
                continue
            name = f.replace(".v", "")
            if name_filter and name != name_filter:
                continue
            cases.append((name, os.path.join(group_ref, f), group))
    cases.sort(key=lambda x: x[0])

    if not cases:
        print("[error] no test cases found")
        return False

    results = []
    total_ok = 0
    total_err = 0
    total_fail = 0
    t_start = time.time()

    for name, path, group in cases:
        with open(path, encoding="utf-8") as f:
            source = f.read()

        macro_table = {}
        directive_lines: list[str] = []
        original_source = source
        if expand_macros:
            from preprocessor import preprocess
            source, macro_table, directive_lines = preprocess(source, RULES_DIR)

        tokens = lex.tokenize(source)
        try:
            ast = parser.parse(tokens)
            if ast is None:
                raise RuntimeError("parser returned None")
            ast = normalize_ast(ast)

            ast = analyzer.analyze(ast)
            scope = analyzer.root_scope
            assert scope is not None, "SemanticAnalyzer did not set root_scope"
            ast = transformer.transform(ast, scope)

            output = renderer.render(ast)

            # 逆向宏：保护字面量 → 全局替换 → 恢复字面量
            if macro_table:
                from preprocessor import protect_and_reverse, load_macro_config
                config = load_macro_config(RULES_DIR)
                define_kw = config.get("directives", {}).get("define", "define")
                output = protect_and_reverse(output, original_source, macro_table,
                                             define_keyword=define_kw)

            # 恢复被剥离的指令行
            if directive_lines:
                header = "\n".join(directive_lines)
                output = header + "\n" + output

            line_count = len([l for l in output.split("\n") if l.strip()])

            # 保存生成文件
            gen_dir = os.path.join(tests_dir, group, "gen")
            os.makedirs(gen_dir, exist_ok=True)
            gen_path = os.path.join(gen_dir, name.replace("ref_", "gen_") + ".v")
            with open(gen_path, "w", encoding="utf-8") as f:
                f.write(output)

            if group == "errors":
                results.append((name, True, line_count, ""))
                total_err += 1
                status = "ERR"
            else:
                results.append((name, True, line_count, ""))
                total_ok += 1
                status = "OK"
        except ParseError as e:
            results.append((name, False, 0, str(e).split("\n")[0]))
            total_fail += 1
            status = "FAIL"
            line_count = 0
        except Exception as e:
            results.append((name, False, 0, str(e)))
            total_fail += 1
            status = "FAIL"
            line_count = 0

        print(f"  {name:25s} {status:5s} {line_count:3d} lines")

    elapsed = time.time() - t_start
    total = total_ok + total_err + total_fail
    print(f"\n{'=' * 40}")
    print(
        f"\n  Total: {total}  OK: {total_ok}  ERR: {total_err}  FAIL: {total_fail}  Time: {elapsed:.1f}s"
    )

    if json_out:
        report = {
            "total": total,
            "ok": total_ok,
            "err": total_err,
            "fail": total_fail,
            "elapsed": round(elapsed, 2),
            "cases": [
                {"name": n, "ok": ok, "lines": ln, "error": err}
                for n, ok, ln, err in results
            ],
        }
        json_path = os.path.join(base_dir, "test_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  Report saved: {json_path}")

    return total_fail == 0


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    json_out = "--json" in sys.argv
    inline_comments = "--inline-comments" in sys.argv
    expand_macros = "--expand-macros" in sys.argv

    pos_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    group_filter = pos_args[0] if len(pos_args) >= 1 else None
    name_filter = pos_args[1] if len(pos_args) >= 2 else None

    if group_filter and group_filter not in ("normal", "errors"):
        print(f"[error] unknown group: {group_filter} (expected normal|errors)")
        sys.exit(1)
    if name_filter:
        name_filter = f"ref_{name_filter}".replace(".v", "")

    ok = run_all(
        verbose=verbose,
        json_out=json_out,
        inline_comments=inline_comments,
        expand_macros=expand_macros,
        group_filter=group_filter,
        name_filter=name_filter,
    )
    sys.exit(0 if ok else 1)
