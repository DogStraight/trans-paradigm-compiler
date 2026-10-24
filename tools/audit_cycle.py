"""tools/audit_cycle.py — 审计循环执行器（只收集，不裁决）。

职责边界：本工具只跑探针、记录原始结果、写账本。**不做判断**——
"这个候选算不算真问题"归 invariant-falsifier（构造反例 + 证据）。
这样分工是为了让"可判定部分"和"需判断部分"不互相污染。

用法：
    python tools/audit_cycle.py                  # 跑所有有探针的维度
    python tools/audit_cycle.py --dim D2         # 只跑一个维度
    python tools/audit_cycle.py --ledger docs/audit-ledger.jsonl
    python tools/audit_cycle.py --list           # 只看注册表
Doc: policy/audit_loop.md（循环协议）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "audit_dimensions.toml"
TODO = "todo"


def load_dimensions() -> list[dict]:
    data = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    return data.get("dimension", [])


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def run_dimension(dim: dict) -> dict:
    """跑一个维度的探针 → {id, status, exit, tail}。status: pass/fail/no_probe。"""
    probe = dim.get("probe", TODO)
    if probe == TODO:
        return {"id": dim["id"], "status": "no_probe", "exit": None,
                "tail": f"无探针（trigger: {dim.get('trigger', '—')}）"}
    started = time.time()
    proc = subprocess.run(probe, shell=True, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "id": dim["id"],
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit": proc.returncode,
        "tail": _last_line(out),
        "seconds": round(time.time() - started, 1),
    }


def _select(dims: list[dict], wanted: list[str]) -> list[dict]:
    """按 --dim 过滤（空 = 全选）。"""
    if not wanted:
        return dims
    keep = set(wanted)
    return [d for d in dims if d["id"] in keep]


def _list_dimensions(dims: list[dict]) -> None:
    for d in dims:
        mark = "probe" if d.get("probe", TODO) != TODO else "todo "
        print(f"  {d['id']} [{mark}] {d['name']} — {d.get('status', 'open')}")


def _print_rows(dims: list[dict], results: list[dict]) -> None:
    labels = {"pass": "PASS", "fail": "FAIL", "no_probe": "SKIP"}
    by_id = {d["id"]: d for d in dims}
    for r in results:
        dim = by_id[r["id"]]
        print(f"  [{labels[r['status']]}] {r['id']} {dim['name']}  {r['tail'][:90]}")
        print(f"         closure: {dim.get('closure', '—')[:100]}")


def _write_ledger(path: Path, results: list[dict]) -> None:
    row = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": results,
    }
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"已写入账本: {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="审计循环执行器（只收集，不裁决）")
    ap.add_argument("--dim", action="append", default=[], help="只跑指定维度 id")
    ap.add_argument("--list", action="store_true", help="只列注册表")
    ap.add_argument("--ledger", type=Path, help="把本轮结果追加到 JSONL 账本")
    args = ap.parse_args(argv)

    dims = _select(load_dimensions(), args.dim)
    if args.list:
        _list_dimensions(dims)
        return 0

    print(f"[审计循环] {len(dims)} 个维度")
    results = [run_dimension(d) for d in dims]
    _print_rows(dims, results)
    ran = sum(1 for r in results if r["status"] != "no_probe")
    failed = sum(1 for r in results if r["status"] == "fail")
    print(f"\n探针 {ran}/{len(results)} 有结果；失败 {failed}；无探针 {len(results) - ran}")
    print("注意：PASS 只表示'探针命令返回 0'，**不等于该维度已关闭**——"
          "关闭需按 policy/audit_loop.md S6 的四条判据。")
    if args.ledger:
        _write_ledger(args.ledger, results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
