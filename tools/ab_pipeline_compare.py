"""ab_pipeline_compare.py — PRE/POST 对拍：证明"用户可见面零变化 / 只有预期变化"。

**只用于对拍，不进日常门禁**；按需/人工跑（分钟级：PRE 需解一份 HEAD 快照）。

只读设计（**任何时候不写工作树**）：
  · PRE = `git archive HEAD` 导出到**临时目录**，在那里跑（`python <tmp>/main.py …`，
    或 `-c` 内联脚本，`sys.path[0]` 指向临时目录 ⇒ 导入的是 HEAD 版引擎）；
  · POST = 当前工作树跑同一命令；
  · 逐输入 diff 诊断 / `success` / `error` / `output`（+ CLI 档的 stdout/exit code）；
  · 临时目录用完即删（`finally`），不碰工作树、不提交、不影响并行中的其它成员。

用法：
    # CLI 档（verilog 用户可见面：`tpc lint --json`；默认跑仓内样本语料）
    python tools/ab_pipeline_compare.py --mode cli
    # CLI 档 + 产物摘要（lint JSON + `tpc format` 渲染文本；零可见变化证据用）
    python tools/ab_pipeline_compare.py --mode cli --products
    python tools/ab_pipeline_compare.py --mode cli --files tests/e2e/samples/errors/e01.v

    # 进程内档（任意语言包；对拍 lint 诊断 + 管线结果）
    python tools/ab_pipeline_compare.py --mode inproc --pack grammar/c \
        --plugins grammar/c/plugins --sources-file _drafts/cases.txt --expect-changed 0

    # 只看差异条数是否等于期望（0 = 零用户可见变化）
    ... --expect-changed 0 --json _drafts/_probe_out/ab.json

判读：`--expect-changed N` 给定时，差异条数必须等于 N（且 verilog 语料快照必须逐字节
相同）；不给则只报告差异、不判失败。差异清单逐条打印 PRE/POST 全值，便于写进报告。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERILOG_GROUPS = ("errors", "lint_err", "normal", "macro")

# 进程内档的采样脚本（在 PRE/POST 各自的状态里执行；stdin 传 JSON 参数）
_INPROC_SNIPPET = r"""
import json, sys
from core.config_registry import ConfigRegistry
from linter.scanner import LinterScanner
from pipeline import run_pipeline_on_source

args = json.loads(sys.stdin.read())
ConfigRegistry.load_language(args["pack"], plugins_dir=args["plugins"])
scanner = LinterScanner(args["pack"], ext_dirs=[args["plugins"]])
out = {}
for src in args["sources"]:
    diags = scanner.scan(src)
    res = run_pipeline_on_source(
        source=src, input_path="case.txt", out_dir=None, quiet=True,
        rules_dir=args["pack"], ext_dirs=[args["plugins"]],
    )
    out[src] = {
        "diags": [[d.code, d.range[0].line, d.range[0].character, bool(d.blocking)] for d in diags],
        "success": bool(res.get("success")),
        "error": str(res.get("error", "")),
        "output": str(res.get("output") or ""),
    }
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
"""


def _python() -> str:
    return sys.executable


def _cli_snapshot(cwd: Path, files: list[str], *, products: bool = False) -> dict:
    """在 `cwd` 状态里逐文件跑 `main.py lint <f> --json --pretty`。

    `products=True` 时再跑 `main.py format <f>`，把渲染文本（stdout+stderr/rc）
    一并纳入快照——"零可见变化"不再只看诊断，还能看到格式/内容产物。
    """
    out: dict[str, dict] = {}
    for rel in files:
        proc = subprocess.run(
            [_python(), "main.py", "lint", rel, "--json", "--pretty"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        item: dict = {"rc": proc.returncode, "stdout": proc.stdout}
        if products:
            fmt = subprocess.run(
                [_python(), "main.py", "format", rel],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            item["format"] = {
                "rc": fmt.returncode,
                "stdout": fmt.stdout,
                "stderr": fmt.stderr,
            }
        out[rel] = item
    return out


def _inproc_snapshot(cwd: Path, payload: dict) -> dict:
    proc = subprocess.run(
        [_python(), "-c", _INPROC_SNIPPET],
        cwd=str(cwd),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"采样失败（cwd={cwd}）:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
    return json.loads(proc.stdout)


def _corpus() -> list[str]:
    files: list[str] = []
    for group in VERILOG_GROUPS:
        d = ROOT / "tests" / "e2e" / "samples" / group
        if d.is_dir():
            files += [
                str(p.relative_to(ROOT)).replace("\\", "/") for p in sorted(d.rglob("*.v"))
            ]
    return files


def _seed_untracked_inputs(dst: Path, files: list[str]) -> int:
    """把 HEAD 副本里缺失的输入文件从工作树补进副本（未跟踪 / 生成的语料）。

    否则 PRE 会因"文件不存在"一律 rc=1，与 POST 比出**假差异**（实测 54 条
    `samples/**/gen/*.v`）——本工具测的是"同一份输入在两个引擎状态下的产物"，
    **输入本身必须两边一致**；缺了就把输入补上，而不是把假差异算进结论。
    """
    n = 0
    for rel in files:
        target = dst / rel
        if target.is_file():
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PRE(HEAD)/POST(工作树) 对拍；只读，不写工作树")
    ap.add_argument("--mode", choices=("cli", "inproc"), default="cli")
    ap.add_argument("--files", nargs="*", default=None, help="CLI 档：输入文件（默认样本语料）")
    ap.add_argument("--pack", default="grammar/c", help="inproc 档：语言包目录")
    ap.add_argument("--plugins", default="grammar/c/plugins", help="inproc 档：插件目录")
    ap.add_argument("--sources-file", default=None, help="inproc 档：每行一个输入文件")
    ap.add_argument("--expect-changed", type=int, default=None, help="期望变化的输入条数")
    ap.add_argument("--json", default=None, help="把结果写到该路径")
    ap.add_argument(
        "--products",
        action="store_true",
        help="CLI 档同时对比 `tpc format` 渲染产物（stdout/rc/stderr）",
    )
    args = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="tpc_ab_pre_"))
    try:
        tar = tmp / "head.tar"
        print(f"[pre] git archive HEAD → {tmp}")
        subprocess.run(
            ["git", "archive", "--format=tar", "-o", str(tar), "HEAD"],
            cwd=str(ROOT),
            check=True,
        )
        subprocess.run(["tar", "-xf", str(tar), "-C", str(tmp)], check=True)
        tar.unlink(missing_ok=True)

        if args.mode == "cli":
            files = args.files or _corpus()
            print(f"[cli] 输入 {len(files)} 个（verilog 用户可见面）")
            seeded = _seed_untracked_inputs(tmp, files)
            if seeded:
                print(f"[pre] 补入 HEAD 副本缺失的输入 {seeded} 个（未跟踪/生成语料）")
            pre = _cli_snapshot(tmp, files, products=args.products)
            post = _cli_snapshot(ROOT, files, products=args.products)
        else:
            if not args.sources_file:
                raise SystemExit("inproc 档需要 --sources-file")
            rels = [
                ln.strip()
                for ln in Path(args.sources_file).read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            payload = {
                "pack": args.pack,
                "plugins": args.plugins,
                "sources": [(ROOT / r).read_text(encoding="utf-8") for r in rels],
            }
            print(f"[inproc] 输入 {len(payload['sources'])} 个（包 {args.pack}）")
            pre = _inproc_snapshot(tmp, payload)
            post = _inproc_snapshot(ROOT, payload)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[cleanup] 临时目录已删：{tmp}")

    changed = [k for k in pre if pre[k] != post.get(k)]
    print(f"\n差异条数: {len(changed)}/{len(pre)}")
    for k in changed:
        print(f"  ── {k[:70]!r}")
        print(f"     PRE : {json.dumps(pre[k], ensure_ascii=False)[:400]}")
        print(f"     POST: {json.dumps(post[k], ensure_ascii=False)[:400]}")
    ok = True
    if args.expect_changed is not None:
        ok = len(changed) == args.expect_changed
        print(f"判据（差异 == {args.expect_changed}）: {'通过 ✓' if ok else '不通过 ✗'}")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"pre": pre, "post": post, "changed": changed}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
