"""tools/audit_cycle.py — 审计循环执行器（只收集，不裁决）。

职责边界：本工具只跑探针、记录原始结果、写账本。**不做判断**——
"这个候选算不算真问题"归 invariant-falsifier（构造反例 + 证据）。
这样分工是为了让"可判定部分"和"需判断部分"不互相污染。

用法：
    python tools/audit_cycle.py                  # 跑所有有探针的维度
    python tools/audit_cycle.py --dim D2         # 只跑一个维度
    python tools/audit_cycle.py --ledger docs/audit-ledger.jsonl
    python tools/audit_cycle.py --list           # 只看注册表
Doc: policy/collaboration.md（任务循环六步 + 审计维度轮）
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


def load_registry() -> dict:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def load_dimensions() -> list[dict]:
    return load_registry().get("dimension", [])


def slot_state(slot: str) -> bool:
    """槽位的装载状态：True = 本轮启用，False = 已卸载（仍在册）。"""
    for item in load_registry().get("pipeline", []):
        if item.get("slot") == slot:
            return bool(item.get("enabled", True))
    return True


def _print_pipeline() -> None:
    rows = load_registry().get("pipeline", [])
    on = [r["slot"] for r in rows if r.get("enabled", True)]
    off = [r["slot"] for r in rows if not r.get("enabled", True)]
    print(f"[管线] 装载 {len(on)} 槽：{', '.join(on) or '—'}")
    print(f"[管线] 卸载 {len(off)} 槽（仍在册）：{', '.join(off) or '—'}")


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
    proc = subprocess.run(
        probe, shell=True, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
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


def _append_row(path: Path, payload: dict) -> None:
    """往 JSONL 账本追加一行（ledger 与 retro 共用；**单一实现**）。

    `newline="\n"` 是必须的：Windows 上按默认 newline 写会把 LF 翻成 CRLF，
    而本仓行尾门禁（`tests/policy/test_eol_normalized.py`）要求工作区一律 LF。
    """
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_ledger(path: Path, results: list[dict], judgement: str = "") -> None:
    """本轮结果 + 人判结论 → JSONL 账本（一行一轮）。"""
    _append_row(path, {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "judgement": judgement,
        "results": results,
    })
    print(f"已写入账本: {path}")


def _collect(dims: list[dict]) -> list[dict]:
    """按 collect 槽装载状态跑探针；卸载时返回空（不报失败）。"""
    _print_pipeline()
    if not slot_state("collect"):
        print("[卸载] collect 槽本轮未启用——跳过全部探针（仍可落账/自省）")
        return []
    print(f"[审计循环] {len(dims)} 个维度")
    return [run_dimension(d) for d in dims]


def _print_summary(results: list[dict]) -> None:
    ran = sum(1 for r in results if r["status"] != "no_probe")
    failed = sum(1 for r in results if r["status"] == "fail")
    print(f"\n探针 {ran}/{len(results)} 有结果；失败 {failed}；无探针 {len(results) - ran}")
    print("注意：PASS 只表示'探针命令返回 0'，**不等于该维度已关闭**——"
          "关闭需按 policy/collaboration.md「审计维度轮」的四条判据。")


RETRO = ROOT / "docs" / "audit-retro.jsonl"


def _write_retro(note: str) -> None:
    """retro 槽：记录制度改进候选（**只记录，不立即改制度**）。"""
    _append_row(RETRO, {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "retro": note})
    print(f"已写入自省账本: {RETRO}")


def _finish(args, results: list[dict]) -> None:
    if args.judgement:
        print(f"人判（探针有效性）：{args.judgement}")
    if args.ledger:
        _write_ledger(args.ledger, results, args.judgement)
    if slot_state("retro") and args.retro:
        _write_retro(args.retro)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="审计循环执行器（只收集，不裁决）")
    ap.add_argument("--dim", action="append", default=[], help="只跑指定维度 id")
    ap.add_argument("--list", action="store_true", help="只列注册表")
    ap.add_argument("--ledger", type=Path, help="把本轮结果追加到 JSONL 账本")
    ap.add_argument("--judgement", default="",
                    help="人判的「探针有效性复核」结论（每轮开局必写）")
    ap.add_argument("--retro", default="",
                    help="retro 槽：本轮制度改进候选（只记录，不立即改制度；可写「无」）")
    args = ap.parse_args(argv)

    dims = _select(load_dimensions(), args.dim)
    if args.list:
        _list_dimensions(dims)
        return 0
    results = _collect(dims)
    _print_rows(dims, results)
    _print_summary(results)
    _finish(args, results)
    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
