#!/usr/bin/env python3
"""tools/scan_test_redundancy.py — 测试用例同构冗余扫描（审查会话复用）

检什么：**同一文件内、结构相同、仅字面量/名字不同**的测试函数组——
即"同范式重复 case"。这类组是参数化（pytest.mark.parametrize）的候选，
不是"测试多"的候选：覆盖要保，重复要消。

不检什么（避免假阳）：
- 跨文件同构（不同模块的测试不该合并）
- 短函数（body < 4 句，参数化收益低于可读性损失）
- 只有 2–3 个成员的小组（默认阈 4，--min-group 可调）
- 跨类同构（分组在类内隔离；模块级与类方法也分开）

安全约束（重要）：本工具**只报告**，不改文件。参数化改动必须自己保证
`pytest --collect-only` 的收集数前后相等（覆盖不丢）；建议流程：
    1) 记录改动前收集数
    2) 逐函数精确删除 + 插入 parametrize（勿按"首末行区间"删除——
       区间内可能夹着非目标测试）
    3) 再记录收集数，必须相等

另检 `min_pack_baseline.json` 锚定：引擎测试的 node id 被该基线记录，
参数化会改 id（`::test_x` → `::test_x[case]`），须串行重录基线。

用法：
    python tools/scan_test_redundancy.py                 # 报告
    python tools/scan_test_redundancy.py --min-group 5   # 只看 >=5 成员组
    python tools/scan_test_redundancy.py --json out.json
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Blank(ast.NodeTransformer):
    """把字面量与名字抹成占位，保留调用/断言/控制流结构。"""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.Constant(value="<L>")

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.Name(id="<N>", ctx=node.ctx)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.arg(arg="<A>")


def _skeleton(fn: ast.FunctionDef) -> str:
    module = ast.Module(body=list(fn.body), type_ignores=[])
    return ast.dump(_Blank().visit(module))


def _baseline_files() -> set[str]:
    """min_pack_baseline 锚定的测试文件（参数化会改 node id）。"""
    p = ROOT / "tools" / "min_pack_baseline.json"
    if not p.is_file():
        return set()
    data = json.loads(io.open(p, encoding="utf-8").read())
    out: set[str] = set()
    for nid in data.get("passed", []):
        head = nid.split("::")[0].split(".")
        for cut in range(len(head), 0, -1):
            cand = ROOT / ("/".join(head[:cut]) + ".py")
            if cand.is_file():
                out.add(cand.relative_to(ROOT).as_posix())
                break
    return out


def _is_test_fn(fn: object, min_body: int) -> bool:
    """是否受检测试函数（`test*` 且函数体够长——太短参数化收益低于可读性损失）。"""
    return (
        isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and fn.name.startswith("test")
        and len(fn.body) >= min_body
    )


def _group_scope(scope: list, min_body: int) -> dict[str, list[ast.FunctionDef]]:
    """一个作用域（模块体 / 类体）内按骨架分组。"""
    local: dict[str, list[ast.FunctionDef]] = defaultdict(list)
    for sub in scope:
        if _is_test_fn(sub, min_body):
            local[_skeleton(sub)].append(sub)
    return local


def _collect_groups(
    tree: ast.Module, min_body: int
) -> dict[str, list[ast.FunctionDef]]:
    """模块级测试函数 + `Test*` 类方法 → {骨架: 成员}。

    分组按"类内 / 模块内"隔离：不同类的同名方法不互相合并
    （类方法的骨架键加 `#class:<类名>:` 前缀）。
    """
    groups = dict(_group_scope(tree.body, min_body))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for sig, members in _group_scope(node.body, min_body).items():
                groups[f"#class:{node.name}:{sig}"] = members
    return groups


def scan(min_group: int = 4, min_body: int = 4) -> list[dict]:
    anchored = _baseline_files()
    findings: list[dict] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        try:
            tree = ast.parse(io.open(path, encoding="utf-8", errors="ignore").read())
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for members in _collect_groups(tree, min_body).values():
            if len(members) < min_group:
                continue
            findings.append({
                "file": rel,
                "count": len(members),
                "reducible": len(members) - 1,
                "baseline_anchored": rel in anchored,
                "members": [{"name": m.name, "line": m.lineno} for m in members],
            })
    findings.sort(key=lambda f: (-f["count"], f["file"]))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="测试同构冗余扫描（只报告）")
    ap.add_argument("--min-group", type=int, default=4, help="最小组成员数（默认 4）")
    ap.add_argument("--min-body", type=int, default=4, help="最小函数体语句数（默认 4）")
    ap.add_argument("--json", metavar="PATH", help="写出 JSON 清单")
    args = ap.parse_args(argv)

    findings = scan(args.min_group, args.min_body)
    total = sum(f["reducible"] for f in findings)
    print("=" * 78)
    print("测试同构冗余扫描（只报告：候选=可参数化，不是可删覆盖）")
    print("=" * 78)
    print(f"\n同构组 {len(findings)} 个；若全部参数化，可减少 {total} 个测试函数\n")
    for f in findings:
        mark = "  [baseline 锚定：参数化须重录]" if f["baseline_anchored"] else ""
        print(f"[{f['count']:2d}] {f['file']}{mark}")
        names = ", ".join(m["name"] for m in f["members"][:6])
        more = " ..." if f["count"] > 6 else ""
        print(f"     {names}{more}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[json] {args.json}")
    print("\n改法：pytest.mark.parametrize 表驱动；收集数前后必须相等（覆盖不丢）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
