"""min_pack_probe.py — 最小语言包探针（行为面基线；gap 判据 1）。

把**默认语言包**换成最小骨架包跑引擎测试，记录"哪些引擎测试仍绿"：

- **仍绿** = 该测试走的是引擎通用面（不依赖任何语言包的声明/语义）；
- **变红** = 该测试依赖某个语言包的声明或语义——可能是它本就属语言包测试（正常），
  也可能是**引擎里的语义渗透**（要查）。

⚠ 只覆盖**被测路径**（与 gap 档三条判据同一局限）：结论只能表述为"已知渗透面收敛"，
**不能**表述为"引擎已语言无关"。

⚠ **一律串行跑**（工具默认补 `-n 0`，见 `_serialize`）：探针**故意让一个进程里混跑两种
语言**——默认包 = 探针包，而大量引擎测试显式加载 verilog；本仓已记载"多语言同进程有真实
串味史"（`tests/README.md`），结果因此随 xdist 的 worker 分配漂移。实测（`tests/engine`，
**同一份代码**）并行三次 = **1126 / 1122 / 1120** 仍绿；**在基线提交上复跑也复现不出基线**
（1120 + 6 项假回归）。改串行后同一子集两次逐项相同（351）。故基线必须**串行**建立与
比对；并行结果只能当"大致规模"，**不可作回归判据**。

⚠ **只比对"通过的集合"**：`failed` / `errored` 的边界同样会漂（同一用例随分配落"失败"
或"报错"，总数不变）。故 `compare` 只认 `passed`；计数仅供人看。

⚠ **基线与"测试 id 集合"绑定**：测试被**增删改名**（哪怕引擎行为没变）也会表现为
"回归 + 新变绿"**成对**出现。实测踩到过——一次测试搬迁造成 **27 进 / 27 出**（总数
不变），逐条核对全是自己挪的测试。故：① 报告按**模块聚合**（先看"回归"是否整块落在
少数模块、且同名测试出现在"新变绿"里）；② 测试重组后**必须重记基线**，且重记前要能
**逐条解释**差异——解释不了就别重记（否则等于把真回归洗掉）。

机制（**零引擎改动**）：`$TPC_CONFIG` 是官方支持的用户配置覆盖点
（`core/_user_config.py` 优先级 1）→ 写一份临时配置把 `grammar` 指向探针包；子进程里
`core.define.DEFAULT_RULES_DIR` 即该包（import 期从配置派生，故必须**进程级**隔离，
不能同进程 monkeypatch——各模块 `from core.define import DEFAULT_RULES_DIR` 已复制值）。

用法::

    python tools/min_pack_probe.py                  # 跑并与基线比对（有回归 → exit 1）
    python tools/min_pack_probe.py --record         # 跑并写基线（需说明原因）
    python tools/min_pack_probe.py --target tests/engine
    python tools/min_pack_probe.py --pack grammar/c4
    python tools/min_pack_probe.py -- -x            # 透传 pytest 参数（`--` 之后）

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

def _by_module(ids: list[str]) -> list[tuple[str, int]]:
    """按模块聚合测试 id（`::` 前部分），计数降序。

    用途：一眼分辨**真回归**与**测试重组**——若"回归"整块落在少数模块上、且那些模块
    的同名测试出现在"新变绿"里，那就是改名/搬迁，不是行为变化（实测踩到过：一次搬迁
    造成 27 进 27 出，逐条核对全是自己挪的测试）。
    """
    counts: dict[str, int] = {}
    for tid in ids:
        mod = tid.split("::")[0]
        counts[mod] = counts.get(mod, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


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
    for label, ids in (
        ("⚠ 回归（曾绿今不绿）", diff["regressed"]),
        ("↑ 新变绿", diff["newly_passing"]),
    ):
        if not ids:
            continue
        print(f"  {label} {len(ids)} 项，按模块：")
        for mod, n in _by_module(ids):
            print(f"    {n:4d}  {mod}")
        for tid in ids[:10]:
            print(f"         - {tid}")
        if len(ids) > 10:
            print(f"         …（另 {len(ids) - 10} 项）")


def _serialize(extra: list[str]) -> list[str]:
    """补 `-n 0`（串行）——**必需项，不是性能选择**。

    探针故意让一个进程里混跑两种语言（默认包 = 探针包，而大量引擎测试显式加载
    verilog），而本仓多语言同进程有真实串味史 → 并行结果随 worker 分配漂移（同一份
    代码实测 1126 / 1122 / 1120，在基线提交上复跑也复现不出基线）。串行（固定顺序）
    才可复现，故基线与比对一律串行。用户显式给了并行参数则尊重其选择（那时只当
    "大致规模"看，别当判据）。
    """
    explicit = any(
        a in ("-n", "--numprocesses")
        or a.startswith("--numprocesses=")
        or a.startswith("-n")
        for a in extra
    )
    return extra if explicit else ["-n", "0", *extra]


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
    result = run_probe(args.pack, targets, _serialize(list(extra)))

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

    diff = compare(baseline, result)
    _report(result, diff)  # 先出数：口径不符时也要看得到规模
    for key, what in (("pack", "探针包"), ("targets", "目标集")):
        if baseline.get(key) != result.get(key):
            print(
                f"  [口径不一致] {what}：基线 {baseline.get(key)!r} "
                f"vs 当前 {result.get(key)!r}——基线与该口径绑定，请重新 --record"
            )
            return 1
    if diff["regressed"]:
        print("  ✗ 存在回归：曾有引擎测试在此包下仍绿，现在不绿了")
        return 1
    print("  ✓ 无回归")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
