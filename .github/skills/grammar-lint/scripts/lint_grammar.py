#!/usr/bin/env python3
"""
grammar-lint — TOML 语法规则静态检查

扫描 grammar/rules_verilog/ 目录下的所有规则文件，
检查常见配置错误和反模式。

用法:
    python lint_grammar.py [--rules-dir PATH]
"""

import os
import re
import sys
import tomllib
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional

# ── 配置 ──

DEFAULT_RULES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "grammar", "rules_verilog",
)

# ── 检查结果 ──

class LintIssue:
    SEVERITY_ERROR = "error"
    SEVERITY_WARN = "warning"
    SEVERITY_INFO = "info"

    def __init__(self, severity: str, file: str, rule: str, message: str):
        self.severity = severity
        self.file = file
        self.rule = rule
        self.message = message

    def __str__(self) -> str:
        sev = {"error": "E", "warning": "W", "info": "I"}.get(self.severity, "?")
        ctx = f" [{self.rule}]" if self.rule else ""
        return f"  {sev}  {self.file}{ctx}  {self.message}"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "file": self.file,
            "rule": self.rule,
            "message": self.message,
        }


# ── 加载器 ──

def load_rules(rules_dir: str) -> Tuple[dict, Dict[str, str]]:
    """加载所有规则，返回 (rules_dict, rule_to_file)"""
    all_rules: dict = {}
    rule_to_file: Dict[str, str] = {}

    for fname in sorted(os.listdir(rules_dir)):
        if not fname.endswith(".toml") or fname.startswith("_"):
            continue
        fpath = os.path.join(rules_dir, fname)
        with open(fpath, "rb") as f:
            data = tomllib.load(f)
        for rule_name in data:
            if rule_name == "file_rules":
                continue
            if rule_name in all_rules:
                print(f"  W  [duplicate] Rule '{rule_name}' defined in both "
                      f"{rule_to_file[rule_name]} and {fname}")
            all_rules[rule_name] = data[rule_name]
            rule_to_file[rule_name] = fname

    return all_rules, rule_to_file


# ── 检查器 ──

def extract_refs(prod_str: str) -> List[str]:
    """从产生式字符串提取 @RuleName 引用"""
    return re.findall(r'@([A-Za-z_]\w*)', prod_str)


def extract_max_n(prod_str: str) -> int:
    """提取产生式中最大的 $N 编号"""
    nums = re.findall(r'\$(\d+)', prod_str)
    return max((int(n) for n in nums), default=0)


def check_rules(rules: dict, rule_to_file: Dict[str, str]) -> List[LintIssue]:
    issues: List[LintIssue] = []

    for name, cfg in rules.items():
        src = rule_to_file.get(name, "?")
        parser = cfg.get("parser", {})
        renderer = cfg.get("renderer", {})

        prods: List[str] = parser.get("production", [])
        node_cfg = parser.get("node", {})
        end_case: List[str] = parser.get("end_case", [])
        block_start = parser.get("block_start")
        block_end = parser.get("block_end")
        inline = parser.get("inline", False)
        pratt = parser.get("pratt", False)
        atomic = parser.get("atomic", False)

        # ── 1. 缺少 production ──
        has_block_start = block_start is not None and isinstance(block_start, str)
        RENDER_ONLY_RULES = {"UnaryOp", "BinaryOp", "TernaryOp",
                              "bracket.l_square_bracket", "bracket.r_square_bracket"}
        if name in RENDER_ONLY_RULES:
            pass  # 这些规则仅供 renderer 使用，无需 production
        elif not prods and not has_block_start and not pratt and not atomic:
            issues.append(LintIssue(
                LintIssue.SEVERITY_ERROR, src, name,
                "No production, block_start, pratt, or atomic defined",
            ))

        # ── 2. 引用不存在的规则 ──
        all_refs = set()
        for prod in prods:
            all_refs.update(extract_refs(prod))

        for ref in all_refs:
            if ref not in rules:
                issues.append(LintIssue(
                    LintIssue.SEVERITY_ERROR, src, name,
                    f"References undefined rule '{ref}'",
                ))

        # ── 3. 循环引用检测（跳过 Pratt 规则和 Expression 层级）──
        CYCLE_SKIP = {"Expression", "PrimaryExpr", "MulExpr", "AddExpr",
                      "CompareExpr", "LogicAndExpr", "LogicOrExpr"}
        if pratt or name in CYCLE_SKIP:
            pass  # Pratt 规则通过解析器处理循环，不检测
        else:
            def has_cycle(current: str, visited: Set[str], path: Set[str]) -> bool:
                if current in CYCLE_SKIP:
                    return False
                if current in path:
                    return True
                if current in visited:
                    return False
                visited.add(current)
                path.add(current)
                cfg = rules.get(current, {})
                if cfg and cfg.get("parser", {}).get("pratt"):
                    path.discard(current)
                    return False
                prods_cfg = cfg.get("parser", {}).get("production", [])
                for p in prods_cfg:
                    for ref in extract_refs(p):
                        if has_cycle(ref, visited, path.copy()):
                            return True
                path.discard(current)
                return False

            if has_cycle(name, set(), set()):
                issues.append(LintIssue(
                    LintIssue.SEVERITY_WARN, src, name,
                    "Circular reference detected",
                ))

        # ── 4. $N 节点映射越界 ──
        max_prod_idx = len(prods)
        for attr_name, mapping in node_cfg.items():
            if isinstance(mapping, str):
                refs_in_mapping = re.findall(r'\$(\d+)', mapping)
                for n_str in refs_in_mapping:
                    n = int(n_str)
                    if n > max_prod_idx:
                        issues.append(LintIssue(
                            LintIssue.SEVERITY_ERROR, src, name,
                            f"Node mapping '{attr_name}' references ${n} "
                            f"but only {max_prod_idx} production(s) exist",
                        ))
            elif isinstance(mapping, list):
                for item in mapping:
                    if isinstance(item, str):
                        for n_str in re.findall(r'\$(\d+)', item):
                            n = int(n_str)
                            if n > max_prod_idx:
                                issues.append(LintIssue(
                                    LintIssue.SEVERITY_ERROR, src, name,
                                    f"Node mapping '{attr_name}' references ${n} "
                                    f"but only {max_prod_idx} production(s) exist",
                                ))

        # ── 5. end_case 中引用不存在的 token ──
        # (end_case 是 token 类型，不是规则名，暂时不检查)

        # ── 6. Inline 规则有多于一个属性映射 ──
        if inline and len(node_cfg) > 1:
            issues.append(LintIssue(
                LintIssue.SEVERITY_WARN, src, name,
                f"Inline rule has {len(node_cfg)} attribute mappings, "
                f"expected 1 (only the first is used by inline flattening)",
            ))

        # ── 7. Atomic 规则没有 end_case ──
        if atomic and not end_case:
            issues.append(LintIssue(
                LintIssue.SEVERITY_INFO, src, name,
                "Atomic rule has no end_case, might match greedily",
            ))

        # ── 8. block_start 但无 block_end ──
        if block_start is not None and block_end is None:
            issues.append(LintIssue(
                LintIssue.SEVERITY_WARN, src, name,
                f"Has block_start='{block_start}' but no block_end",
            ))

        # ── 9. renderer layout 中的 ref 引用不存在的属性 ──
        def check_layout_refs(layout: dict, prefix: str = ""):
            for key, val in layout.items():
                if key == "ref":
                    # 检查 ref 的值是否是 node 映射中定义过的属性
                    attr_name = val if isinstance(val, str) else str(val)
                    if attr_name not in node_cfg and attr_name not in ("value",):
                        # 有些 ref 指向子节点名称而非属性，较难静态判断
                        pass  # 暂时忽略
                elif isinstance(val, dict):
                    check_layout_refs(val, f"{prefix}.{key}")
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            check_layout_refs(item, f"{prefix}.{key}")

        check_layout_refs(renderer)

    # ── 全局检查 ──

    # 10. 未使用的规则（不被任何其他规则引用）
    used_rules: Set[str] = set()
    for name, cfg in rules.items():
        parser = cfg.get("parser", {})
        prods = parser.get("production", [])
        for prod in prods:
            used_rules.update(extract_refs(prod))

    # 通过 renderer layout ref 引用的规则也算使用
    for name, cfg in rules.items():
        renderer = cfg.get("renderer", {})
        def collect_layout_refs(d):
            if isinstance(d, dict):
                for k, v in d.items():
                    if k == "ref" and isinstance(v, str):
                        used_rules.add(v)
                    else:
                        collect_layout_refs(v)
            elif isinstance(d, list):
                for item in d:
                    collect_layout_refs(item)
        collect_layout_refs(renderer)

    # 通过 entry、block 机制使用的规则
    for name, cfg in rules.items():
        parser = cfg.get("parser", {})
        entry = parser.get("entry")
        if entry:
            used_rules.add(entry)

    # 入口规则（被 parse() 或 parse_block_body 直接使用）
    ENTRY_RULES = {"Root", "ModuleDecl", "Comment"}
    # 规则名称本身就是 token 类型（用于 renderer 直接引用，无需 production）
    TOKEN_RULES = {"UnaryOp", "BinaryOp", "TernaryOp",
                   "bracket.l_square_bracket", "bracket.r_square_bracket"}

    for name in rules:
        if name in TOKEN_RULES:
            continue
        if name not in used_rules and name not in ENTRY_RULES:
            src = rule_to_file.get(name, "?")
            issues.append(LintIssue(
                LintIssue.SEVERITY_INFO, src, name,
                "Rule is defined but never referenced",
            ))

    return issues


# ── 入口 ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Grammar rule linter")
    parser.add_argument("--rules-dir", default=DEFAULT_RULES_DIR, help="Rules directory")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if not os.path.isdir(args.rules_dir):
        print(f"Error: rules directory not found: {args.rules_dir}")
        sys.exit(1)

    rules, rule_to_file = load_rules(args.rules_dir)
    issues = check_rules(rules, rule_to_file)

    if args.format == "json":
        import json
        report = {
            "total_rules": len(rules),
            "total_issues": len(issues),
            "issues": [i.to_dict() for i in issues],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]

        print(f"\n{'='*60}")
        print(f"  Grammar Lint Report — {os.path.basename(args.rules_dir)}")
        print(f"  Rules: {len(rules)}  Issues: {len(issues)} "
              f"(E:{len(errors)} W:{len(warnings)} I:{len(infos)})")
        print(f"{'='*60}")

        for severity, label in [("error", "Errors"), ("warning", "Warnings"), ("info", "Infos")]:
            items = [i for i in issues if i.severity == severity]
            if items:
                print(f"\n  {label}:")
                for item in items:
                    print(f"  {item}")

        if not issues:
            print("\n  No issues found.\n")


if __name__ == "__main__":
    main()
