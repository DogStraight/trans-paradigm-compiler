"""tools/check_test_isolation.py — 测试隔离对照：共享进程 vs 每块一个干净进程。

Doc: tests/README.md（隔离与顺序巡检节）

动机：进程级隔离最直接的做法是 pytest-forked，但它走 `os.fork`——Windows 没有
（实测 `hasattr(os, "fork")` 为 False），CI 矩阵里 windows-latest 直接不可用。
故这里的进程级隔离用**子进程**实现：把选中的测试切块，每块在**全新解释器**里
跑一遍（跨平台、零新依赖）。

它回答两个问题：

1. **隔离档是否绿**：某用例在干净进程里也失败 → 与进程内状态无关（它自己或
   环境的问题），拿到的是"必现的最小复现"。
2. **两档差异**（`--compare`）：这是幽灵 flake 的分型依据——
   - 只在**共享档**失败 = 进程内状态泄漏 / 顺序污染（L1 登记表该管的，见
     `core/global_state.py`；发现即补登记表或改 fixture 作用域）；
   - 只在**隔离档**失败 = 该用例隐式依赖同进程里其它文件留下的状态（跨文件隐式
     依赖，在 CI 分片、单文件重跑、`loadfile` 换序时同样会爆）。
   两个方向都报——它们都是"换一种跑法就变脸"的同一类病。

设计取舍：
- **不进日常门禁**：全量隔离档要起上百个解释器（分钟级），与 `eval_*` 同档
  （人工/定期跑）；nightly 跑 smoke 对照档。
- **子进程内用 `-n 0`**：父进程已经按块并行，块内再并行只会互抢 CPU。
- **默认 `PYTHONHASHSEED=0`**：隔离档要的是可复现，不再引入第二个变量；要抖
  哈希种子用 `--random-hashseed`。
- **粒度可选**：`file`（默认，成本低，覆盖跨文件污染）与 `test`（最强隔离，
  单用例一进程，慢——定位单个用例时用）。

用法：
    python tools/check_test_isolation.py                        # 全量，每文件一进程
    python tools/check_test_isolation.py -m smoke               # 只 smoke 层
    python tools/check_test_isolation.py --compare -m smoke     # 与共享进程档对照
    python tools/check_test_isolation.py --hashseed-scan 8 -m smoke   # 哈希种子扫描
    python tools/check_test_isolation.py --granularity test tests/e2e/test_real_fidelity.py
    python tools/check_test_isolation.py --jobs 8 --list        # 只列分组清单

三个档回答同一问题的不同侧面（"同一份代码换跑法会不会变脸"）：
- 隔离档：换**进程**（每块全新解释器）——进程内状态泄漏的探针；
- 共享档（`--compare`）：单进程跑完全集——与隔离档差异即"换跑法就变脸"；
- 哈希种子档（`--hashseed-scan N`）：换**PYTHONHASHSEED**（xdist 各 worker 天然
  不同）——输出依赖 set/dict 迭代顺序时，同一输入在不同进程会给出不同结果。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# nodeid 形如 `tests/x/test_y.py::test_z[参数-含 空格]`——参数 id 里可以有空格，
# 故按 "路径.py::" 切分而不是按空白切分。
# 文件部分可能为空：目标在 rootdir 之外时（如临时目录）pytest 会把路径省略，
# 短摘要行变成 `FAILED ::test_needs - ...`（实测），此时按用例名辨认。
_NODEID_RE = re.compile(r"^(?P<path>\S+\.py)::(?P<rest>.+)$")
_FAIL_LINE_RE = re.compile(r"^(?:FAILED|ERROR)\s+(?P<nodeid>\S*::\S.*)$")
# pytest 摘要的尾缀（"7 passed in 3.25s" / "1 failed in 2s (0:00:02)"）
_TIME_SUFFIX_RE = re.compile(r"\s+in\s+[\d.]+s(?:\s*\([\d:. ]+\))?\s*$")


@dataclass(frozen=True)
class ChunkResult:
    """一个块（文件或单个用例）的执行结果。"""

    name: str
    returncode: int
    failed: tuple[str, ...]
    summary: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# ── 子进程调用 ──────────────────────────────────────────────────────────────

def _pytest_env(random_hashseed: bool, hashseed: int | None = None) -> dict[str, str]:
    """子进程环境：强制 UTF-8 管道（含中文的 nodeid 不能按本机代码页解码）。

    `hashseed` 指定时写死该值；`random_hashseed` 则显式不设（每进程随机）。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if hashseed is not None:
        env["PYTHONHASHSEED"] = str(hashseed)
    elif random_hashseed:
        env.pop("PYTHONHASHSEED", None)
    else:
        env["PYTHONHASHSEED"] = "0"
    return env


def _stable_summary(summary: str) -> str:
    """摘要去计时：`7 passed in 3.25s` → `7 passed`。

    哈希种子扫描要判"结果是否漂移"，耗时不同不是漂移（实测：不去计时会把每个
    种子都报成 drift）。
    """
    return _TIME_SUFFIX_RE.sub("", summary).strip()


def _run_pytest(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _safe_run(args: list[str], env: dict[str, str]) -> ChunkResult:
    """跑一个子进程并归结果；启动级失败（如命令行过长）也算失败块。"""
    try:
        proc = _run_pytest(args, env)
    except OSError as exc:  # 命令行超长 / 解释器不可用等启动级错误
        return ChunkResult(args[-1] if args else "(?)", 1, (), f"子进程启动失败：{exc}")
    output = (proc.stdout or "") + (proc.stderr or "")
    return ChunkResult("", proc.returncode, _failing_ids(output), _summary_line(output))


def _selection_args(targets: list[str], marker: str | None, keyword: str | None) -> list[str]:
    args = list(targets)
    if marker:
        args += ["-m", marker]
    if keyword:
        args += ["-k", keyword]
    return args


def _parse_nodeids(output: str) -> list[str]:
    """从 `--collect-only -q` 输出里取 nodeid（跳过汇总行/警告）。"""
    ids: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if _NODEID_RE.match(line):
            ids.append(line)
    return ids


def _normalize_id(nodeid: str) -> str:
    """归一化 nodeid：仓内路径压成相对形式（反斜杠统一成正斜杠）。

    子进程拿到的目标可能是绝对路径（如 `--granularity test` 逐用例跑），pytest
    会把那个写法回显在 FAILED 行里——两档比对前必须归一，否则同一失败在
    "绝对 vs 相对" 两种写法下会被算成两个不同的失败。
    """
    path, sep, rest = nodeid.partition("::")
    if not sep or not path:  # 无文件部分（rootdir 之外的省略形态）原样返回
        return nodeid
    rel = os.path.relpath(path, _ROOT)
    if rel.startswith(".."):
        return nodeid
    return f"{rel.replace(os.sep, '/')}::{rest}"


def _compare_key(nodeid: str) -> str:
    """比对键：无文件部分的 nodeid（省略形态）退到用例名去比。

    文件部分被省略时双方（隔离档/共享档）都省略，退到用例名仍能正确配对；
    若保留原样，一个带路径一个不带就会被当成两个不同的失败。
    """
    return nodeid[2:] if nodeid.startswith("::") else nodeid


def _failing_ids(output: str) -> tuple[str, ...]:
    """从 `-q` 输出里取失败/错误的 nodeid（短摘要段）。

    只留 nodeid、丢掉 " - 异常信息" 尾巴：两档比对必须按 **nodeid** 比——尾巴里
    的异常文本在两档下可能不同（例如栈里有别的东西），带着比会把同一失败算成两个。
    """
    out: list[str] = []
    for raw in output.splitlines():
        m = _FAIL_LINE_RE.match(raw.strip())
        if m:
            nodeid = re.split(r"\s+-\s+", m.group("nodeid"), maxsplit=1)[0].strip()
            out.append(_normalize_id(nodeid))
    return tuple(dict.fromkeys(out))


def _summary_line(output: str) -> str:
    """取结果摘要行；没有就回退到末行非空输出。

    回退很重要：收集/导入期错误（或子进程异常退出）没有 "N passed/failed"
    行——若只回 "无摘要行"，真因就被藏掉了（工具的第一职责是能定位）。
    """
    for raw in reversed(output.splitlines()):
        line = raw.strip()
        if line and ("passed" in line or "failed" in line or "error" in line.lower()):
            return line.strip("=").strip()
    for raw in reversed(output.splitlines()):
        if raw.strip():
            return raw.strip()[:200]
    return "（无输出）"


# ── 目标路径解析 ────────────────────────────────────────────────────────────

def _abs_target(name: str, roots: list[str]) -> str:
    """把收集输出里的名字解析成子进程可直接使用的绝对路径。

    `--collect-only -q` 给的 nodeid 是**相对 rootdir** 的，而 rootdir 不一定
    是仓库根（目标在仓库外时 pytest 会把那个目录当 rootdir，实测直接拿
    `test_a.py` 去跑得到 "file or directory not found"）。所以按候选根依次试
    存在性，而不是简单拼 cwd。
    """
    if os.path.isabs(name):
        return name
    for root in roots:
        cand = os.path.abspath(os.path.join(root, name))
        if os.path.exists(cand):
            return cand
    tried = ", ".join(os.path.abspath(os.path.join(r, name)) for r in roots)
    return f"__NOT_FOUND__{name}（已试：{tried}）"


def _abs_nodeid(nodeid: str, roots: list[str]) -> str:
    """nodeid → 绝对文件 + 用例部分。"""
    path, _, rest = nodeid.partition("::")
    return f"{_abs_target(path, roots)}::{rest}" if rest else _abs_target(path, roots)


# ── 分组与执行 ──────────────────────────────────────────────────────────────

def group_chunks(nodeids: list[str], granularity: str) -> dict[str, list[str]]:
    """按粒度分组：file → 文件路径为键；test → 每个用例一块。"""
    if granularity == "test":
        return {nid: [nid] for nid in nodeids}
    chunks: dict[str, list[str]] = {}
    for nid in nodeids:
        chunks.setdefault(nid.split("::", 1)[0], []).append(nid)
    return chunks


def _run_chunk(
    name: str, items: list[str], env: dict[str, str], granularity: str, roots: list[str],
) -> ChunkResult:
    # 块内串行（-n 0 覆盖 addopts 的 -n auto）：并行已在父进程按块做
    cmd = [_abs_nodeid(items[0], roots)] if granularity == "test" else [_abs_target(name, roots)]
    res = _safe_run([*cmd, "-q", "-n", "0", "--no-header"], env)
    return ChunkResult(name, res.returncode, res.failed, res.summary)


def _run_isolated(
    chunks: dict[str, list[str]], env: dict[str, str], jobs: int, granularity: str,
    roots: list[str], verbose: bool,
) -> list[ChunkResult]:
    """每块一个全新解释器；按 jobs 并行。"""
    results: list[ChunkResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(_run_chunk, name, items, env, granularity, roots): name
            for name, items in chunks.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)
            if verbose or not res.ok:
                flag = "OK  " if res.ok else "FAIL"
                print(f"  [{flag}] {res.name} — {res.summary}")
    return sorted(results, key=lambda r: r.name)


def _run_shared(selection: list[str], env: dict[str, str]) -> ChunkResult:
    """共享进程档：**一个**进程跑完选中集（`-n 0`）。

    刻意关并：xdist 会把文件分到不同 worker——那样"共享"名不副实（实测
    `_drafts` 里两个有隐式依赖的文件在 `-n auto` 下就分到两个 worker，两边都
    报失败，对照失去意义）。一个进程跑完全集才是真正的"共享进程"参照物。

    传原**选择集**（路径 / -m / -k）而不是逐个 nodeid：全量近两千个 id 放进
    一条命令行会撞 Windows 32767 字符上限（WinError 206）。
    """
    res = _safe_run([*selection, "-q", "-n", "0", "--no-header"], env)
    return ChunkResult("(共享进程)", res.returncode, res.failed, res.summary)


def _hashseed_scan(
    selection: list[str], seeds: int,
) -> tuple[list[tuple[int, ChunkResult]], list[int]]:
    """同一选择集在 seeds 个 PYTHONHASHSEED 下各跑一遍（单进程档）。

    返回 (每个种子的结果, 与首个种子结果不同的种子)。差异即"输出/结果依赖
    set|dict 迭代顺序"——xdist 每个 worker 的 seed 不同，这类问题在并行下就是
    换跑法变脸。
    """
    runs: list[tuple[int, ChunkResult]] = []
    drift: list[int] = []
    baseline: tuple[int, tuple[str, ...], str] | None = None
    for seed in range(seeds):
        res = _run_shared(selection, _pytest_env(False, hashseed=seed))
        runs.append((seed, res))
        key = (res.returncode, res.failed, _stable_summary(res.summary))
        if baseline is None:
            baseline = key
        elif key != baseline:
            drift.append(seed)
    return runs, drift


def diff_failures(
    isolated: list[ChunkResult], shared: ChunkResult,
) -> tuple[list[str], list[str]]:
    """返回 (只在共享档失败, 只在隔离档失败)。

    按 `_compare_key` 配对（无文件部分的 nodeid 退到用例名）；展示时回到
    原 nodeid，避免同一失败因写法差异被重复计入。
    """
    iso: dict[str, str] = {}
    for res in isolated:
        for nid in res.failed:
            iso[_compare_key(nid)] = nid
        if not res.ok and not res.failed:
            iso[res.name] = res.name  # 收集/导入期错误：没有 FAILED 行，用块名占位
    shared_by_key: dict[str, str] = {_compare_key(nid): nid for nid in shared.failed}
    if not shared.ok and not shared.failed:
        shared_by_key[shared.name] = shared.name
    shared_only = [shared_by_key[k] for k in shared_by_key.keys() - iso.keys()]
    isolated_only = [iso[k] for k in iso.keys() - shared_by_key.keys()]
    return sorted(shared_only), sorted(isolated_only)


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cli_parser() -> argparse.ArgumentParser:
    """命令行参数定义。"""
    ap = argparse.ArgumentParser(
        prog="check_test_isolation",
        description="测试隔离对照：共享进程 vs 每块一个干净进程（进程级隔离，跨平台）",
    )
    ap.add_argument("targets", nargs="*", default=None, help="测试路径（默认 tests）")
    ap.add_argument("-m", "--marker", default=None, help="pytest marker 表达式（如 smoke）")
    ap.add_argument("-k", "--keyword", default=None, help="pytest -k 表达式")
    ap.add_argument(
        "--granularity", choices=("file", "test"), default="file",
        help="切块粒度：file（默认）或 test（最强隔离，慢）",
    )
    ap.add_argument("--jobs", type=int, default=0, help="并行子进程数（默认 = CPU 核数）")
    ap.add_argument("--compare", action="store_true", help="再跑一次共享进程档并列出差异")
    ap.add_argument(
        "--hashseed-scan", type=int, default=0, metavar="N",
        help="单进程档在 N 个 PYTHONHASHSEED 下各跑一遍，报结果漂移"
    )
    ap.add_argument("--random-hashseed", action="store_true", help="不固定 PYTHONHASHSEED（巡检挡）")
    ap.add_argument("--verbose", action="store_true", help="每个块都打印结果")
    ap.add_argument("--list", action="store_true", help="只列分组清单")
    return ap


def _phase_isolated(
    args: argparse.Namespace,
    env: dict[str, str],
    jobs: int,
    roots: list[str],
    chunks: dict[str, list[str]],
    nodeids: list[str],
) -> tuple[list[ChunkResult], int]:
    """隔离档：逐块新解释器跑 + 报表明细 → (结果, status)。"""
    print(
        f"[info] 用例 {len(nodeids)} 个 → {len(chunks)} 块"
        f"（粒度 {args.granularity}，jobs={jobs}，"
        f"PYTHONHASHSEED={'随机' if args.random_hashseed else '0'}）"
    )
    t0 = time.perf_counter()
    isolated = _run_isolated(chunks, env, jobs, args.granularity, roots, args.verbose)
    elapsed = time.perf_counter() - t0
    bad = [r for r in isolated if not r.ok]
    print(f"[隔离档] {len(isolated) - len(bad)} OK / {len(bad)} FAIL（用时 {elapsed:.0f}s）")
    for res in bad:
        print(f"  FAIL {res.name} — {res.summary}")
        for nid in res.failed:
            # 省略形态（文件部分为空）在报表里补上块名，否则看不出是哪个文件
            shown = f"{res.name}{nid}" if nid.startswith("::") else nid
            print(f"       - {shown}")
    return isolated, (1 if bad else 0)


def _phase_compare(
    selection: list[str],
    env: dict[str, str],
    isolated: list[ChunkResult],
    any_fail: bool,
) -> bool:
    """共享进程档对照（`--compare`）→ 是否存在两档差异。"""
    print("[info] 共享进程档：单进程（-n 0）跑完选中集——一个进程才叫\"共享\"")
    t1 = time.perf_counter()
    shared = _run_shared(selection, env)
    print(f"[共享档] {shared.summary}（用时 {time.perf_counter() - t1:.0f}s）")
    shared_only, isolated_only = diff_failures(isolated, shared)
    if shared_only:
        print(f"[差异] 只在共享档失败（进程内状态泄漏/顺序污染）：{len(shared_only)}")
        for nid in shared_only:
            print(f"       - {nid}")
    if isolated_only:
        print(f"[差异] 只在隔离档失败（隐式依赖同进程其它文件的状态）：{len(isolated_only)}")
        for nid in isolated_only:
            print(f"       - {nid}")
    if shared_only or isolated_only:
        return True
    if not any_fail:
        print("[OK] 两档一致且全绿——该集合没有进程内状态耦合")
    return False


def _phase_hashseed(selection: list[str], seeds: int, any_fail: bool) -> bool:
    """哈希种子扫描（`--hashseed-scan`）→ 是否存在结果漂移。"""
    print(f"[info] 哈希种子扫描：{seeds} 个 PYTHONHASHSEED × 单进程档")
    t2 = time.perf_counter()
    runs, drift = _hashseed_scan(selection, seeds)
    for seed, res in runs:
        flag = "  <-- 与 seed 0 不一致" if seed in drift else ""
        print(f"  seed={seed:<3} {res.summary}{flag}")
    print(f"[哈希种子档] 用时 {time.perf_counter() - t2:.0f}s；漂移种子：{drift or '无'}")
    if not drift:
        if not any_fail:
            print("[OK] 结果不随哈希种子漂移")
        return False
    for seed in drift:
        res = next((r for s, r in runs if s == seed), None)
        for failed in (res.failed if res else ()):
            print(f"       - seed={seed}: {failed}")
    return True


def main(argv: list[str] | None = None) -> int:
    """隔离对照 CLI 入口：收集 → 切块 → 隔离档（+ 可选对照/哈希扫描）。"""
    args = _cli_parser().parse_args(argv)

    targets = args.targets or ["tests"]
    env = _pytest_env(args.random_hashseed)
    jobs = args.jobs or (os.cpu_count() or 4)
    selection = _selection_args(targets, args.marker, args.keyword)
    # 候选根：仓库根 + 各目标目录（nodeid 相对 rootdir，不一定是仓库根）
    roots = [_ROOT, *(os.path.abspath(t) for t in targets)]

    collect = _run_pytest([*selection, "--collect-only", "-q", "-n", "0"], env)
    nodeids = _parse_nodeids(collect.stdout)
    if not nodeids:
        print("[error] 未收集到任何用例：")
        print(collect.stdout[-2000:] or collect.stderr[-2000:])
        return 2
    chunks = group_chunks(nodeids, args.granularity)

    if args.list:
        print(f"[info] {len(nodeids)} 个用例，切 {len(chunks)} 块（粒度 {args.granularity}）")
        for name, items in chunks.items():
            print(f"  {name} — {len(items)}")
        return 0

    isolated, status = _phase_isolated(args, env, jobs, roots, chunks, nodeids)
    any_fail = any(not r.ok for r in isolated)
    drift = False
    if args.compare:
        drift = _phase_compare(selection, env, isolated, any_fail)
    if args.hashseed_scan:
        drift = _phase_hashseed(selection, args.hashseed_scan, any_fail) or drift
    if drift:
        status = 1
    if status:
        print("[FAIL] 隔离档有失败或两档存在差异（见上）")
        return status
    print("[OK] 隔离档全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
