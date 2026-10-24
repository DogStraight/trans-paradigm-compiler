#!/usr/bin/env python3
"""policy/check_invariants.py — 不变量清单门禁（防"清单腐烂成新的封闭幻觉"）

为什么有它：`docs/invariants.toml` 把"该证伪什么"变成**数据**（项目特定），
skill/协议只提供证伪流程。但**数据会腐烂**——规则/测试被删后，清单里仍写着
指向已不存在锚点的条目，于是"我们只检查这 5 条"退化成"这 5 条里有 2 条没人管"。
本门禁把腐烂变成红灯。

校验项（全部可判定，零枚举）：
  1. 字段齐全且非空；`id` 唯一且形如 INV-*
  2. `verification` ∈ {mechanized, procedural}
  3. mechanized ⇒ `gate` 与 `violation_probe` 都必须**可解析**
     （锚点解析到真实文件 + 真实规则 id / 测试函数 / 变异序号）
  4. procedural ⇒ 必须给 `manual_check`（否则它只是口号）
  5. `statement` 与 `violation` 不得雷同（把"是什么"和"怎么算违反"混为一谈）

锚点格式：
  policy/<file>.py#<RULE_ID>            → 该脚本 collect_findings().results 含该规则
  tests/<path>.py::<test_func>          → 该文件里有同名 def test_*
  tools/check_gate_efficacy.py#<序号>    → `_MUTATIONS` 里存在该序号（1-based）

用法：
    python policy/check_invariants.py             # 校验并打印清单
    python policy/check_invariants.py --json      # 机器可读
Doc: docs/invariants.toml（数据面与字段说明）
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "invariants.toml"

# 必须有"一句话实质"的文本字段（`id`/`verification` 是枚举/标识，不参与长度检查）
TEXT_FIELDS = ("statement", "violation", "observable", "known_pass")
REQUIRED_FIELDS = ("id",) + TEXT_FIELDS + ("verification",)
MECHANIZED = "mechanized"
PROCEDURAL = "procedural"
MIN_TEXT = 12  # 一句话至少这么长才算"说了点什么"（防占位符）


@dataclass
class Issue:
    invariant: str
    field: str
    message: str


@dataclass
class Report:
    invariants: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def mechanized(self) -> int:
        return sum(1 for i in self.invariants if i.get("verification") == MECHANIZED)


# ── 锚点解析 ──────────────────────────────────────────────────────

def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_inv_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _resolve_policy_rule(root: Path, path: Path, rule: str) -> str | None:
    """`policy/<file>.py#R6` → 该脚本是否真的产出该规则（跑一次 collect_findings）。"""
    if not path.is_file():
        return f"脚本不存在：{path.relative_to(root)}"
    mod = _load_module(path)
    collect = getattr(mod, "collect_findings", None)
    if collect is None:
        return f"{path.name} 没有 collect_findings（不是规则脚本）"
    try:
        report = collect(root)
    except Exception as exc:  # noqa: BLE001 — 门禁自身失败要显式报出
        return f"运行 {path.name} 失败：{exc}"
    return None if rule in getattr(report, "results", {}) else f"规则 {rule} 不在结果里"


def _resolve_test(root: Path, path: Path, func: str) -> str | None:
    if not path.is_file():
        return f"测试文件不存在：{path.relative_to(root)}"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return f"{path.name} 解析失败：{exc}"
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return None if func in names else f"测试函数 {func} 不在 {path.name} 里"


def _resolve_mutation(root: Path, path: Path, index: str) -> str | None:
    if not path.is_file():
        return f"变异表脚本不存在：{path.relative_to(root)}"
    mod = _load_module(path)
    mutations = getattr(mod, "_MUTATIONS", None)
    if mutations is None:
        return f"{path.name} 没有 _MUTATIONS"
    try:
        n = int(index)
    except ValueError:
        return f"变异序号不是整数：{index!r}"
    return None if 1 <= n <= len(mutations) else f"变异 #{n} 越界（共 {len(mutations)} 条）"


def resolve_anchor(root: Path, anchor: str) -> str | None:
    """锚点 → None（可解析）| 错误说明。格式非法也算错。"""
    if "#" not in anchor and "::" not in anchor:
        return f"锚点格式非法（须含 `#` 或 `::`）：{anchor!r}"
    if "::" in anchor:
        path_part, _, func = anchor.partition("::")
        return _resolve_test(root, root / path_part, func)
    path_part, _, target = anchor.rpartition("#")
    path = root / path_part
    if path.name == "check_gate_efficacy.py":
        return _resolve_mutation(root, path, target)
    if path.suffix == ".py":
        return _resolve_policy_rule(root, path, target)
    return f"不认识的锚点类型：{anchor!r}"


# ── 校验 ──────────────────────────────────────────────────────────

def _check_text_fields(item: dict, name: str, rep: Report) -> None:
    """必填 + 一句话实质（防空占位符）。"""
    for f in REQUIRED_FIELDS:
        val = item.get(f)
        if not isinstance(val, str) or not val.strip():
            rep.issues.append(Issue(name, f, "缺失"))
    for f in TEXT_FIELDS:
        val = item.get(f)
        if isinstance(val, str) and 0 < len(val.strip()) < MIN_TEXT:
            rep.issues.append(Issue(name, f, "过短（不足一句话）"))


def _check_identity(item: dict, idx: int, name: str, seen: set[str], rep: Report) -> None:
    """id 唯一 + 命名前缀 + statement/violation 不得雷同。"""
    if name in seen:
        rep.issues.append(Issue(name, "id", "重复"))
    seen.add(name)
    if not name.startswith("INV-"):
        rep.issues.append(Issue(name, "id", "应形如 INV-<主题>"))
    if str(item.get("statement", "")).strip() == str(item.get("violation", "")).strip():
        rep.issues.append(Issue(name, "violation", "与 statement 雷同（没说清怎么算违反）"))


def _check_anchors(item: dict, name: str, rep: Report, root: Path) -> None:
    """mechanized ⇒ gate + violation_probe 可解析；procedural ⇒ 有 manual_check。"""
    kind = item.get("verification")
    if kind == MECHANIZED:
        for f in ("gate", "violation_probe"):
            anchor = item.get(f)
            if not isinstance(anchor, str) or not anchor.strip():
                rep.issues.append(Issue(name, f, "mechanized 必须有锚点"))
                continue
            err = resolve_anchor(root, anchor)
            if err:
                rep.issues.append(Issue(name, f, err))
    elif kind == PROCEDURAL:
        mc = item.get("manual_check")
        if not isinstance(mc, str) or len(mc.strip()) < MIN_TEXT:
            rep.issues.append(Issue(name, "manual_check", "procedural 必须写清人工怎么查"))
    else:
        rep.issues.append(Issue(name, "verification", f"只能是 {MECHANIZED}/{PROCEDURAL}"))


def _validate_entry(idx: int, item: dict, seen: set[str], rep: Report,
                    root: Path = ROOT) -> None:
    name = str(item.get("id") or f"<第 {idx} 条>")
    _check_text_fields(item, name, rep)
    _check_identity(item, idx, name, seen, rep)
    _check_anchors(item, name, rep, root)


def collect(root: Path = ROOT) -> Report:
    rep = Report()
    manifest = root / 'docs' / 'invariants.toml'
    if not manifest.is_file():
        rep.issues.append(Issue("<manifest>", "file", f"找不到 {manifest}"))
        return rep
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    items = data.get("invariant") or []
    if not items:
        rep.issues.append(Issue("<manifest>", "invariant", "清单为空（不变量是数据，不能空）"))
    seen: set[str] = set()
    for idx, item in enumerate(items, 1):
        rep.invariants.append(item)
        _validate_entry(idx, item, seen, rep, root)
    return rep


def _print_report(rep: Report, quiet: bool = False) -> None:
    print(f"[不变量门禁] {len(rep.invariants)} 条（mechanized {rep.mechanized}"
          f" / procedural {len(rep.invariants) - rep.mechanized}）")
    if not quiet:
        for it in rep.invariants:
            print(f"  - {it.get('id')} [{it.get('verification')}] gate={it.get('gate') or '—'}")
    if rep.issues:
        print(f"[FAIL] 清单问题 {len(rep.issues)} 处：")
        for i in rep.issues:
            print(f"  {i.invariant}.{i.field}: {i.message}")
    else:
        print("[PASS] 不变量清单可解析：字段齐全、锚点全部有效")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="不变量清单门禁")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    rep = collect(args.root)
    if args.json:
        print(json.dumps({
            "total": len(rep.invariants),
            "mechanized": rep.mechanized,
            "issues": [i.__dict__ for i in rep.issues],
        }, ensure_ascii=False, indent=2))
    else:
        _print_report(rep, args.quiet)
    return 1 if rep.issues else 0


if __name__ == "__main__":
    sys.exit(main())
