"""ci_rehearsal.py — 本地排练 `ci.yml` 的全部门禁（发布/打标前一条命令自查）。

动机：本仓的门禁**只在推送分支时运行**（`.github/workflows/ci.yml` 的触发是
`push.branches` + `pull_request`，推 tag 不触发）。于是"长期不推送"= 门禁长期不运行
= 静默漂移：0.1.2/0.1.3 两批共 449 个提交从未被 CI 看过，实测已累积 4 类红
（`TODO.md`「测试基础设施」有实测矩阵）。本工具把 CI 的每一步在本地等价跑一遍，
在打标前给出同一份结论——**不必等推送才知道红**。

判读（三态，缺验证不算绿）：
  PASS 该步跑通且退出码 0；
  FAIL 该步退出码非 0（含超时）；
  SKIP 该步在本机无法运行（如没装 pyright）——**SKIP 不等于绿**，整体判 INCOMPLETE。

整体结论：任一 FAIL ⇒ FAIL（exit 1）；否则任一 SKIP ⇒ INCOMPLETE（exit 2）；
全 PASS ⇒ PASS（exit 0）。exit 2 是刻意的：让"没验到"与"验过了"在脚本层面可区分。

用法：
  python tools/ci_rehearsal.py                    # 全量（含 wheel 安装冒烟，~10 分钟）
  python tools/ci_rehearsal.py --skip-wheel       # 跳过打包冒烟（~7 分钟）
  python tools/ci_rehearsal.py --only pyright     # 只跑名字含该子串的步骤
  python tools/ci_rehearsal.py --pyright <path>   # 指定 pyright 可执行文件
  python tools/ci_rehearsal.py --update-baseline  # 见下

⚠ 与 CI 的**已知差异**（写在这里而不是让人以为逐位等价）：
  · pyright 版本：CI 钉 `npx -y pyright@1.1.413`；本工具优先用 PATH 上的 `pyright`，
    其次 `--pyright`，再次 `npx`（离线时失败）——版本不同时会在结论里标注。
  · CLI 冒烟：CI 用安装后的 `tpc`；本工具用 `python main.py`（同一入口函数）。
  · 覆盖率报告只打 TOTAL 行（CI 同样只看门禁通过与否）。
Doc: TODO.md（测试基础设施：CI 排练结果）/ policy/release-checklist.md（发布前跑本工具）
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CI 钉死的 pyright 版本（`ci.yml`：Static type gate）
PYRIGHT_PIN = "1.1.413"
_PYRIGHT_PROJECT = "pyrightconfig.strict.json"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclasses.dataclass
class Step:
    """一个门禁步骤：名字（含匹配用的短名）+ 跑法（callable → (exit_code, output)）。"""

    name: str
    key: str
    run: Callable[[], tuple[int, str]]
    timeout: int = 900


def _text(value: object) -> str:
    """子进程输出统一成 str（TimeoutExpired 的 stdout/stderr 可能是 bytes 或 None）。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _run(argv: list[str], env_extra: dict | None = None, timeout: int = 900):
    """跑子进程 → (exit_code, 合并输出)。超时按占用退出码 124 处理（不是静默跳过）。"""
    env = {**os.environ, **(env_extra or {})}
    try:
        proc = subprocess.run(
            argv,
            cwd=_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"[timeout {timeout}s]\n{_text(exc.stdout)}{_text(exc.stderr)}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _find_pyright(explicit: str | None) -> tuple[list[str] | None, str]:
    """定位 pyright → (argv, 说明)。找不到返回 (None, 原因)。"""
    if explicit:
        return [explicit], f"显式指定 {explicit}"
    found = shutil.which("pyright")
    if found:
        return [found], f"PATH 上的 pyright（{found}）"
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", f"pyright@{PYRIGHT_PIN}"], f"npx pyright@{PYRIGHT_PIN}"
    return None, "本机既无 pyright 也无 npx（`pip install pyright` 到一个 venv 后用 --pyright 指定）"


def _wheel_install_check() -> tuple[int, str]:
    """CI 的第二个 job：build → 独立 venv 装 wheel → 仓库外跑 CLI。

    构建产物落在**临时目录**（不动仓库的 `dist/`）：本工具只做排练，不改工作区状态。
    """
    log: list[str] = []
    outdir = os.path.join(tempfile.gettempdir(), "tpc-ci-rehearsal-dist")
    shutil.rmtree(outdir, ignore_errors=True)
    code, out = _run([sys.executable, "-m", "build", "--no-isolation", "--outdir", outdir],
                     timeout=600)
    log.append(f"[build] exit={code}")
    if code != 0:
        return code, "\n".join(log) + "\n" + out[-1500:]
    wheels = [f for f in os.listdir(outdir) if f.endswith(".whl")]
    if not wheels:
        return 1, "\n".join(log) + "\n[build] 未产出 wheel"
    wheel = os.path.join(outdir, wheels[0])
    log.append(f"[build] {wheels[0]}")

    venv = os.path.join(tempfile.gettempdir(), "tpc-ci-rehearsal-venv")
    shutil.rmtree(venv, ignore_errors=True)
    code, out = _run([sys.executable, "-m", "venv", venv], timeout=300)
    if code != 0:
        return code, "\n".join(log) + "\n[venv] " + out[-800:]
    py = os.path.join(venv, "Scripts" if os.name == "nt" else "bin", "python")
    code, out = _run([py, "-m", "pip", "install", "--quiet", "--no-index", "--no-deps",
                      wheel], timeout=300)
    log.append(f"[install] exit={code}")
    if code != 0:
        return code, "\n".join(log) + "\n" + out[-1200:]

    exe = os.path.join(venv, "Scripts" if os.name == "nt" else "bin", "tpc")
    sample = os.path.join(_ROOT, "tests", "e2e", "samples", "normal", "ref", "ref_simple.v")
    # 从仓库外跑：验证 rules_dir 解析到 site-packages 内的 grammar 包
    proc = subprocess.run(
        [exe, "format", sample],
        cwd=tempfile.gettempdir(),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ}, timeout=300,
    )
    log.append(f"[off-repo CLI] exit={proc.returncode}")
    shutil.rmtree(venv, ignore_errors=True)
    if proc.returncode != 0:
        return proc.returncode, "\n".join(log) + "\n" + (proc.stderr or "")[-800:]
    return 0, "\n".join(log) + "\n[off-repo CLI] OK"


def _cli_check() -> tuple[int, str]:
    """CI 的 `Verify CLI works`：临时 .v 走一遍 format（等价用 main.py 入口）。"""
    sample = os.path.join(tempfile.gettempdir(), "tpc_ci_check.v")
    with open(sample, "w", encoding="utf-8") as f:
        f.write("module m; reg a; endmodule\n")
    code, out = _run([sys.executable, "main.py", "format", sample], timeout=300)
    os.remove(sample)
    return code, out


def _noop_pyright() -> tuple[int, str]:
    """占位：pyright 的 argv 依赖运行期定位结果，实际执行在 main() 里。"""
    return 0, ""


def build_steps() -> list[Step]:
    """CI 步骤表（顺序照 `ci.yml`；pyright 的 argv 在 main() 里按定位结果拼）。"""
    return [
        Step("主回归 pytest -n auto --cov", "pytest",
             lambda: _run([sys.executable, "-m", "pytest", "tests", "-q", "-n", "auto",
                           "--cov"], {"PYTHONHASHSEED": "0"}, timeout=1800), timeout=1800),
        Step("乱序 smoke（TPC_SHUFFLE_SEED=1）", "smoke",
             lambda: _run([sys.executable, "-m", "pytest", "-m", "smoke", "-q"],
                          {"TPC_SHUFFLE_SEED": "1", "PYTHONHASHSEED": "0"}, timeout=600), 600),
        Step("policy: check_hardcode --strict-doc --strict-import", "hardcode",
             lambda: _run([sys.executable, "policy/check_hardcode.py",
                           "--strict-doc", "--strict-import"], timeout=300), 300),
        Step("policy: check_doc_refs", "docrefs",
             lambda: _run([sys.executable, "policy/check_doc_refs.py"], timeout=300), 300),
        Step("pyright strict（静态类型门禁）", "pyright", _noop_pyright, 600),
        Step("edge corpus", "edge",
             lambda: _run([sys.executable, "tests/edge/run_edge.py"], timeout=900), 900),
        Step("fuzz smoke 500", "fuzz",
             lambda: _run([sys.executable, "tests/fuzz/run_fuzz.py", "--iters", "500"],
                          timeout=900), 900),
        Step("CLI 冒烟（main.py format）", "cli", _cli_check, 300),
        Step("wheel 安装冒烟（build + venv + 仓库外 CLI）", "wheel",
             _wheel_install_check, 1200),
    ]


def summarize(results: list[tuple[Step, str, int, float, str]]) -> tuple[str, str]:
    """(整体结论, 矩阵文本)。两条纪律：SKIP 不算绿；**一步都没跑也不算绿**。"""
    if not results:
        return "INCOMPLETE", "  （未运行任何步骤——筛选条件没命中？「没验」不等于「验过了」）"
    verdict = PASS
    lines = []
    for step, verdict_i, code, secs, _ in results:
        if verdict_i == FAIL:
            verdict = FAIL
        elif verdict_i == SKIP and verdict != FAIL:
            verdict = "INCOMPLETE"
        lines.append(f"  {verdict_i:<5} {step.name}  [{secs:.0f}s, exit {code}]")
    return verdict, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="本地排练 ci.yml 的全部门禁")
    ap.add_argument("--only", default="", help="只跑名字/短名含该子串的步骤")
    ap.add_argument("--skip-wheel", action="store_true", help="跳过打包安装冒烟")
    ap.add_argument("--pyright", default=None, help="pyright 可执行文件路径")
    args = ap.parse_args(argv)

    pyright_argv, pyright_note = _find_pyright(args.pyright)
    steps = build_steps()
    if args.skip_wheel:
        steps = [s for s in steps if s.key != "wheel"]
    if args.only:
        steps = [s for s in steps if args.only in s.key or args.only in s.name]

    print(f"[ci_rehearsal] 仓库根 {_ROOT}")
    print(f"[ci_rehearsal] pyright：{pyright_note}")
    print(f"[ci_rehearsal] 共 {len(steps)} 步\n")

    results: list[tuple[Step, str, int, float, str]] = []
    for step in steps:
        # pyright 的 argv 依赖定位结果，故单独走一条分支；「没定位到」= SKIP（不算绿）。
        # 注意写成**单条件**判断：复合条件（A and B）在 pyright 下不产生类型收窄。
        if step.key == "pyright" and pyright_argv is None:
            print(f"  SKIP  {step.name} —— {pyright_note}")
            results.append((step, SKIP, -1, 0.0, pyright_note))
            continue
        t0 = time.time()
        if step.key == "pyright":
            if pyright_argv is None:  # 已由上面 continue 排除，此处仅为类型收窄
                raise AssertionError("unreachable")
            code, out = _run([*pyright_argv, "--project", _PYRIGHT_PROJECT],
                             timeout=step.timeout)
        else:
            code, out = step.run()
        secs = time.time() - t0
        verdict_i = PASS if code == 0 else FAIL
        print(f"  {verdict_i:<5} {step.name}  [{secs:.0f}s, exit {code}]")
        if verdict_i == FAIL:
            tail = "\n".join(out.strip().splitlines()[-12:])
            print("        ── 尾部输出 ──")
            for line in tail.splitlines():
                print(f"        {line}")
        results.append((step, verdict_i, code, secs, out))

    overall, matrix = summarize(results)
    print(f"\n[ci_rehearsal] 整体结论：{overall}")
    print(matrix)
    if overall == "PASS":
        return 0
    return 1 if overall == FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
