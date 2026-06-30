"""
从 grammar/rules_verilog/ 和 rules_verilog_ext/ 的 TOML 规则
自动生成 @RuleRef 调用关系 Mermaid 图。

用法：
    python scripts/gen_grammar_graph.py                                       # 全图（143节点）
    python scripts/gen_grammar_graph.py -d 04_statements                       # 仅某目录
    python scripts/gen_grammar_graph.py -d 02_declarations                     # 声明目录子图
    python scripts/gen_grammar_graph.py -n Declarator --depth 2                # 单规则+2层纵深
    python scripts/gen_grammar_graph.py -n Identifier --invert                 # 谁引用了 Identifier
    python scripts/gen_grammar_graph.py -o grammar_graph.md -f                 # 含 EXT 注入线
"""

import argparse
import glob
import os
import sys
import tomllib
from collections import defaultdict


def _clean_ref(name: str) -> str:
    """去掉 @RuleName 后的 ? * + 后缀"""
    while name and name[-1] in "?*+":
        name = name[:-1]
    return name


def _safe_id(name: str) -> str:
    """转义为 Mermaid 合法节点 ID"""
    return name.replace("-", "_").replace("/", "_").replace(".", "_")


def scan_rules(
    rules_dir: str,
) -> tuple[dict[str, list[str]], dict[str, set[str]], set[str]]:
    """扫描 TOML 规则目录。

    返回:
        refs: 规则→[引用的规则]
        inverted: 规则→[被哪些规则引用]
        all_rules: 所有规则名集合
    """
    refs: dict[str, list[str]] = {}
    inverted: dict[str, set[str]] = defaultdict(set)
    all_rules: set[str] = set()

    for fpath in glob.glob(os.path.join(rules_dir, "**/*.toml"), recursive=True):
        basename = os.path.basename(fpath)
        if basename.startswith("_"):
            continue
        try:
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            continue

        for rule_name, rule in data.items():
            if not isinstance(rule, dict):
                continue
            all_rules.add(rule_name)
            parser = rule.get("parser", {})
            if isinstance(parser, dict):
                prod = parser.get("production", [])
            else:
                prod = rule.get("production", [])
            if not isinstance(prod, list):
                continue

            deps: list[str] = []
            _collect_refs(prod, deps)
            if deps:
                refs[rule_name] = deps
                for d in deps:
                    inverted[d].add(rule_name)

    return refs, dict(inverted), all_rules


def _collect_refs(prod: list, deps: list[str]) -> None:
    for elem in prod:
        if isinstance(elem, str):
            if elem.startswith("@"):
                deps.append(_clean_ref(elem[1:]))
        elif isinstance(elem, list):
            _collect_refs(elem, deps)


def scan_inject(rules_dir: str) -> dict[str, list[str]]:
    inject: dict[str, list[str]] = defaultdict(list)
    for fpath in glob.glob(os.path.join(rules_dir, "**/*.toml"), recursive=True):
        basename = os.path.basename(fpath)
        if basename.startswith("_"):
            continue
        try:
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            continue
        for rule_name, rule in data.items():
            if not isinstance(rule, dict):
                continue
            inj = rule.get("inject")
            if isinstance(inj, dict) and "targets" in inj:
                for t in inj["targets"]:
                    if isinstance(t, str) and t.startswith("@"):
                        inject[rule_name].append(_clean_ref(t[1:]))
                    elif isinstance(t, str):
                        inject[rule_name].append(t)
    return dict(inject)


def _filter_by_dir(
    all_rules: set[str],
    rules_dir: str,
    subdir: str,
) -> set[str]:
    """只保留指定子目录中定义的规则名"""
    result: set[str] = set()
    target = subdir.replace("/", os.sep).replace("\\", os.sep)
    for fpath in glob.glob(os.path.join(rules_dir, "**/*.toml"), recursive=True):
        rel = os.path.relpath(fpath, rules_dir)
        if not rel.startswith(target):
            continue
        basename = os.path.basename(fpath)
        if basename.startswith("_"):
            continue
        try:
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            continue
        for rule_name in data:
            if isinstance(rule_name, str):
                result.add(rule_name)
    return result


def _subgraph(
    refs: dict[str, list[str]],
    inverted: dict[str, set[str]],
    all_rules: set[str],
    focus_rules: set[str],
    depth: int = 0,
    show_incoming: bool = False,
) -> tuple[dict[str, list[str]], set[str]]:
    """以 focus_rules 为种子扩散 depth 层生成子图"""
    result_rules: set[str] = set(focus_rules)
    result_refs: dict[str, list[str]] = {}

    # 向外扩散
    current = set(focus_rules)
    for _ in range(depth + 1):
        nxt: set[str] = set()
        for r in current:
            deps = refs.get(r, [])
            keep = [d for d in deps if d in all_rules]
            if keep:
                result_refs[r] = keep
                nxt.update(keep)
                result_rules.update(keep)
        current = nxt

    if show_incoming:
        current = set(focus_rules)
        for _ in range(depth + 1):
            nxt: set[str] = set()
            for r in current:
                callers = inverted.get(r, set())
                for c in callers:
                    if c in all_rules:
                        result_rules.add(c)
                        nxt.add(c)
                        result_refs.setdefault(c, []).append(r)
            current = nxt

    return result_refs, result_rules





def generate_mermaid(
    refs: dict[str, list[str]],
    all_rules: set[str],
    inject: dict[str, list[str]] | None = None,
) -> str:
    lines = ["```mermaid", "graph LR"]

    for rule in sorted(all_rules):
        lines.append(f'    {_safe_id(rule)}["{rule}"]')

    for src, targets in sorted(refs.items()):
        safe_src = _safe_id(src)
        for tgt in targets:
            if tgt not in all_rules:
                continue
            lines.append(f"    {safe_src} --> {_safe_id(tgt)}")

    if inject:
        lines.append("")
        lines.append("    %% --- EXT inject edges ---")
        for ext_rule, targets in sorted(inject.items()):
            safe_ext = _safe_id(ext_rule)
            for tgt in targets:
                if tgt in all_rules:
                    lines.append(f"    {safe_ext} -.-> {_safe_id(tgt)}")

    lines.append("```")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="生成语法规则调用关系 Mermaid 图")
    ap.add_argument("-o", "--output", help="输出文件路径（默认输出到控制台）")
    ap.add_argument("-f", "--full", action="store_true", help="包含 EXT 注入边（虚线）")
    ap.add_argument(
        "-d", "--dir", help="只显示某子目录的规则（如 '04_statements' '02_declarations'）"
    )
    ap.add_argument("-n", "--name", help="以某规则为中心展开邻居图")
    ap.add_argument("--depth", type=int, default=1, help="邻居图扩散层数（默认 1）")
    ap.add_argument("--invert", action="store_true", help="邻居图也包含入边（谁引用了我）")
    args = ap.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_dir = os.path.join(project_root, "grammar", "rules_verilog")
    ext_dir = os.path.join(project_root, "grammar", "rules_verilog_ext")

    refs, inverted, all_rules = scan_rules(rules_dir)
    ext_refs, ext_inverted, ext_rules = scan_rules(ext_dir)

    all_rules.update(ext_rules)
    refs.update(ext_refs)
    for k, v in ext_inverted.items():
        if k in inverted:
            inverted[k].update(v)
        else:
            inverted[k] = set(v)

    inject = scan_inject(ext_dir)

    if args.name:
        if args.name not in all_rules:
            print(f"错误：规则 '{args.name}' 不存在", file=sys.stderr)
            sys.exit(1)
        refs, all_rules = _subgraph(
            refs, inverted, all_rules, {args.name}, args.depth, args.invert
        )
    elif args.dir:
        focus = _filter_by_dir(all_rules, rules_dir, args.dir)
        if not focus:
            print(f"错误：目录 '{args.dir}' 中未找到规则", file=sys.stderr)
            sys.exit(1)
        refs, all_rules = _subgraph(refs, inverted, all_rules, focus, 0)

    mermaid = generate_mermaid(refs, all_rules, inject if args.full else None)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid + "\n")
        print(f"已写入 {args.output}")
    else:
        print(mermaid)

    edge_count = sum(len(v) for v in refs.values())
    isolated = len(all_rules) - len(refs)
    print(f"\n--- 统计 ---", file=sys.stderr)
    print(f"节点: {len(all_rules):>3}  边: {edge_count:>3}  孤立: {isolated:>3}", file=sys.stderr)


if __name__ == "__main__":
    main()
