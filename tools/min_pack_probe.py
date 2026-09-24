"""min_pack_probe.py — 最小语言包探针（行为面基线；gap 判据 1）。

把**默认语言包**换成最小骨架包跑引擎测试，记录"哪些引擎测试仍绿"：

- **仍绿** = 该测试走的是引擎通用面（不依赖任何语言包的声明/语义）；
- **变红** = 该测试依赖某个语言包的声明或语义——可能是它本就属语言包测试（正常），
  也可能是**引擎里的语义渗透**（要查）。

⚠ 只覆盖**被测路径**（与 gap 档三条判据同一局限）：结论只能表述为"已知渗透面收敛"，
**不能**表述为"引擎已语言无关"。

⚠ **只比对"通过的集合"**：实测 `failed` / `errored` 的边界会漂（同一次基线两次跑：
146/130 vs 141/135，总数不变——同一用例随 xdist 分配在不同 worker 里可能落"失败"
或"报错"），而 `passed` 集合逐项相同。故 `compare` 只认 `passed`；计数仅供人看。

机制（**零引擎改动**）：`$TPC_CONFIG` 是官方支持的用户配置覆盖点
（`core/_user_config.py` 优先级 1）→ 写一份临时配置把 `grammar` 指向探针包；子进程里
`core.define.DEFAULT_RULES_DIR` 即该包（import 期从配置派生，故必须**进程级**隔离，
不能同进程 monkeypatch——各模块 `from core.define import DEFAULT_RULES_DIR` 已复制值）。

用法::

    python tools/min_pack_probe.py                  # 跑并与基线比对（有回归 → exit 1）
    python tools/min_pack_probe.py --record         # 跑并写基线（需说明原因）
    python tools/min_pack_probe.py --target tests/engine
    python tools/min_pack_probe.py --pack grammar/c4
    python tools/min_pack_probe.py -n 0 -- -x       # 透传 pytest 参数（`--` 之后）

按需跑，**不进日常门禁**（分钟级）——见 tools/README.md。判据与实测清单见
`docs/gaps/gap-language-penetration.md`。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 探针包：仓库既有的**迷你语言包**（无插件、4 个 token 文件，最小且固定）。
# 换它 = 换"引擎在几乎没有语言声明时还能做什么"的基准；一旦选定就不要随意改
# （基线与该包绑定）。
_PACK_DEFAULT = "grammar/yaml"

_TARGET_DEFAULT = ["tests/engine"]

_BASELINE_PATH = os.path.join("tools", "min_pack_baseline.json")


# ── 跑探测 ──

def _write_probe_config(tmpdir: str, pack: str) -> str:
    """写临时用户配置（`grammar` → 探针包），返回路径（供 `$TPC_CONFIG`）。"""
    path = os.path.join(tmpdir, "tpc_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"grammar": pack}, f, ensure_ascii=False, indent=2)
    return path


def run_probe(pack: str, targets: list[str], extra: list[str]) -> dict:
    """子进程跑 pytest（`$TPC_CONFIG` → 探针包），返回结果摘要。"""
    with tempfile.TemporaryDirectory(prefix="tpc_min_pack_") as tmpdir:
        cfg = _write_probe_config(tmpdir, pack)
        xml = os.path.join(tmpdir, "report.xml")
        cmd = [
            sys.executable, "-m", "pytest", *targets,
            "--junitxml", xml, "-q", "--no-header", *extra,
        ]
        env = dict(os.environ, TPC_CONFIG=cfg)
        proc = subprocess.run(cmd, cwd=_ROOT, env=env, text=True)
        if not os.path.isfile(xml):
            raise SystemExit(
                f"[min-pack-probe] pytest 未产出报告（exit {proc.returncode}）"
                f"——收集阶段就失败了？先手工跑：\n  {' '.join(cmd)}"
            )
        return _parse_report(xml, pack, targets)


def _parse_report(xml_path: str, pack: str, targets: list[str]) -> dict:
    """junit XML → {通过的测试 id, 计数}。"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    passed: list[str] = []
    failed = 0
    errored = 0
    skipped = 0
    for suite in suites:
        for case in suite.iter("testcase"):
            tid = f"{case.get('classname', '')}::{case.get('name', '')}"
            kinds = {child.tag for child in case}
            if "failure" in kinds:
                failed += 1
            elif "error" in kinds:
                errored += 1
            elif "skipped" in kinds:
                skipped += 1
            else:
                passed.append(tid)
    return {
        "pack": pack,
        "targets": list(targets),
        "passed": sorted(passed),
        "passed_count": len(passed),
        "failed_count": failed,
        "errored_count": errored,
        "skipped_count": skipped,
    }


# ── 基线读写与比对 ──

def load_baseline(path: str = _BASELINE_PATH) -> dict | None:
    full = os.path.join(_ROOT, path)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def write_baseline(result: dict, path: str = _BASELINE_PATH) -> str:
    full = os.path.join(_ROOT, path)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return full


def compare(baseline: dict, current: dict) -> dict:
    """基线 vs 当前：`regressed` = 曾绿今不绿（要查），`newly_passing` = 新变绿。"""
    was = set(baseline.get("passed", []))
    now = set(current.get("passed", []))
    return {
        "regressed": sorted(was - now),
        "newly_passing": sorted(now - was),
        "stable": len(was & now),
    }


# ── CLI ──

def _report(result: dict, diff: dict | None) -> None:
    print(
        f"[min-pack-probe] pack={result['pack']} "
        f"targets={','.join(result['targets'])}"
    )
    print(
        f"  仍绿 {result['passed_count']} / 变红 {result['failed_count']} "
        f"/ 报错 {result['errored_count']} / 跳过 {result['skipped_count']}"
    )
    if diff is None:
        return
    print(f"  与基线相同 {diff['stable']}")
    if diff["regressed"]:
        print(f"  ⚠ 回归（曾绿今不绿）{len(diff['regressed'])} 项：")
        for tid in diff["regressed"][:20]:
            print(f"    - {tid}")
        if len(diff["regressed"]) > 20:
            print(f"    …（另 {len(diff['regressed']) - 20} 项）")
    if diff["newly_passing"]:
        print(f"  ↑ 新变绿 {len(diff['newly_passing'])} 项（可能是普适面扩大）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="最小语言包探针（行为面基线；gap 判据 1）",
    )
    ap.add_argument("--pack", default=_PACK_DEFAULT, help=f"探针包（默认 {_PACK_DEFAULT}）")
    ap.add_argument(
        "--target", action="append", default=None,
        help=f"pytest 目标（可多次；默认 {' '.join(_TARGET_DEFAULT)}）",
    )
    ap.add_argument("--record", action="store_true", help="写基线（覆盖）")
    ap.add_argument("--json", action="store_true", help="输出当前结果 JSON")
    ap.add_argument("--baseline", default=_BASELINE_PATH, help="基线文件路径")
    args, extra = ap.parse_known_args(argv)
    if extra and extra[0] == "--":
        extra = extra[1:]

    targets = args.target or list(_TARGET_DEFAULT)
    result = run_probe(args.pack, targets, list(extra))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.record:
        path = write_baseline(result, args.baseline)
        _report(result, None)
        print(f"  已写基线：{os.path.relpath(path, _ROOT)}")
        return 0

    baseline = load_baseline(args.baseline)
    if baseline is None:
        _report(result, None)
        print(f"  [基线不存在] 先跑 --record 建立基线（{args.baseline}）")
        return 0

    for key, what in (("pack", "探针包"), ("targets", "目标集")):
        if baseline.get(key) != result.get(key):
            print(
                f"  [口径不一致] {what}：基线 {baseline.get(key)!r} "
                f"vs 当前 {result.get(key)!r}——基线与该口径绑定，请重新 --record"
            )
            return 1

    diff = compare(baseline, result)
    _report(result, diff)
    if diff["regressed"]:
        print("  ✗ 存在回归：曾有引擎测试在此包下仍绿，现在不绿了")
        return 1
    print("  ✓ 无回归")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
