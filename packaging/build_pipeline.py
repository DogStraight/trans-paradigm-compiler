"""build_pipeline.py — 功能切面打包管线（单一文件 exe）。

把需要的命令切面（format/lint/expand/config...）打包进单一可执行文件：
按 packaging/facets.json 规格 → 生成入口脚本（packaging/entries/）→
Nuitka onefile（内置 Python + 引擎 + 语法包 + PE 署名）→ SHA256。

用法:
    python packaging/build_pipeline.py tpc-fmt         # 构建指定切面
    python packaging/build_pipeline.py --all           # 构建 facets.json 全部
    python packaging/build_pipeline.py tpc-fmt --dry-run   # 只生成入口，不构建

产物:
    dist/<name>.exe          — 单一文件可执行
    dist/SHA256SUMS.txt      — 校验和（追加）

前置: pip install nuitka + C 编译器（MSVC Build Tools / MinGW）。
设计: main.py 的 _register_subparsers(sub, allow) 支持命令裁剪——入口脚本
只挂载 spec 里的 facets，行为与 `tpc <cmd>` 完全一致（同一分发函数）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = os.path.dirname(os.path.abspath(__file__))
_ENTRIES = os.path.join(_PKG, "entries")
_SPEC = os.path.join(_PKG, "facets.json")
_DIST = os.path.join(_ROOT, "dist")
_RULES_REL = "grammar/verilog"

sys.path.insert(0, _ROOT)

from core import __version__  # noqa: E402
from attribution import (  # noqa: E402 — 同目录模块（packaging/ 非包）
    AUTHOR_NAME,
    AUTHOR_EMAIL,
    AI_CO_AUTHOR,
    REPO_URL,
    credits_text,
)

_ENTRY_TEMPLATE = '''"""%(name)s_entry.py — 由 packaging/build_pipeline.py 生成，勿手改。

Facets: %(facets)s
"""

import argparse
import sys

sys.path.insert(0, %(root)r)

from main import _register_subparsers, _dispatch  # noqa: E402
from core import __version__  # noqa: E402

CREDITS_TEXT = %(credits)r


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=%(prog)r,
        description=%(description)r,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--credits", action="store_true",
        help="Show author / source / license info and exit",
    )
    # 子命令可裁剪：只挂载本切面的命令；--credits/--version 不要求子命令
    sub = parser.add_subparsers(dest="command")
    _register_subparsers(sub, allow=%(allow)r)
    args = parser.parse_args()
    if args.credits:
        print(CREDITS_TEXT, end="")
        return
    if args.command is None:
        parser.error("no command given (available: %(facets)s)")
    _dispatch(args)


if __name__ == "__main__":
    main()
'''


def _load_spec() -> dict:
    with open(_SPEC, encoding="utf-8") as f:
        return json.load(f)


def _generate_entry(name: str, spec: dict) -> str:
    os.makedirs(_ENTRIES, exist_ok=True)
    facets = spec["facets"]
    entry = _ENTRY_TEMPLATE % {
        "name": name,
        "facets": ", ".join(facets),
        "root": _ROOT,
        "credits": credits_text(name, __version__),
        "prog": name,
        "description": spec["file_description"],
        "allow": facets,
    }
    path = os.path.join(_ENTRIES, f"{name.replace('-', '_')}_entry.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(entry)
    return path


def _nuitka_cmd(name: str, spec: dict, entry: str) -> list[str]:
    rules_dir = os.path.join(_ROOT, _RULES_REL)
    # 插件 postpass/transform .py 显式 include：这些脚本经 load_postpasses
    # 动态 import（importlib 按路径加载），Nuitka 静态收集看不到——实测
    # include-data-dir 不保证携带 .py（checks/ 聚类后新插件的 postpass 曾
    # 整体缺失 → exe 启动即崩 ValueError postpass 模块不存在）。逐个
    # --include-data-files 显式携带（含 checks/syntax 等聚类子目录）。
    data_files: list[str] = []
    for root, dirs, fnames in os.walk(rules_dir):
        dirs[:] = [d for d in dirs if not d.startswith(("__", "."))]
        for fn in fnames:
            if fn.endswith(".py"):
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, _ROOT)
                # Nuitka 要求单参数 `--include-data-files=src=dest`（分开传报错）
                data_files.append(f"--include-data-files={src}={rel}")
    return [
        sys.executable, "-m", "nuitka", "--onefile",
        # 正确性优先：Nuitka 模块缓存会串旧入口编译产物（实测：换入口后
        # 不清理缓存，exe 载荷仍是旧入口内容）。打包低频，每次全量重编译。
        "--clean-cache=all",
        "--output-dir=dist",
        f"--output-filename={name}.exe",
        f"--include-data-dir={rules_dir}={_RULES_REL}",
        *data_files,
        f"--company-name={AUTHOR_NAME}",
        f"--product-name={spec['product_name']}",
        f"--file-description={spec['file_description']}",
        f"--product-version={__version__}",
        f"--file-version={__version__}",
        f"--copyright=Copyright (c) {__version__} {AUTHOR_NAME} "
        f"<{AUTHOR_EMAIL}> — AI Co-author: {AI_CO_AUTHOR} — Source: {REPO_URL}",
        entry,
    ]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(name: str, spec: dict, dry_run: bool = False) -> None:
    print(f"== build {name}  facets={spec['facets']}")
    entry = _generate_entry(name, spec)
    print(f"   entry: {entry}")
    if dry_run:
        print("   (dry-run: 跳过 Nuitka 构建)")
        return
    cmd = _nuitka_cmd(name, spec, entry)
    print("   nuitka: " + " ".join(cmd[:4]) + " ...")
    r = subprocess.run(cmd, cwd=_ROOT)
    if r.returncode != 0:
        sys.exit(f"nuitka build failed for {name} (exit {r.returncode})")
    exe = os.path.join(_DIST, f"{name}.exe")
    if not os.path.isfile(exe):
        sys.exit(f"missing build output: {exe}")
    digest = _sha256(exe)
    os.makedirs(_DIST, exist_ok=True)
    sums = os.path.join(_DIST, "SHA256SUMS.txt")
    lines = []
    if os.path.isfile(sums):
        with open(sums, encoding="ascii") as f:
            lines = [l for l in f.read().splitlines() if l and name not in l]
    lines.append(f"SHA256  {digest}  {name}.exe")
    with open(sums, "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")
    print(f"   done: {exe} ({os.path.getsize(exe) / 1e6:.1f} MB)")
    print(f"   sha256: {digest}")
    _smoke_test(name, exe, spec, dry_run)


def _smoke_test(name: str, exe: str, spec: dict, dry_run: bool) -> None:
    """构建后冒烟：对样本文件跑 exe 的各切面命令，任一失败即构建失败。

    防静默坏包（实测教训：checks/ 插件 postpass .py 打包缺失 → exe 启动
    即崩，但构建本身成功）。样本用无宏的真实语料（serv_top，1 module 纯
    generate——lint/format/check 三命令都能过）。
    """
    if dry_run:
        return
    facets = spec["facets"]
    sample = os.path.join(_ROOT, "tests", "e2e", "samples", "real", "ref", "ref_serv_top.v")
    probes = []
    if "format" in facets:
        probes.append(("format", ["format", sample]))
    if "lint" in facets:
        probes.append(("lint", ["lint", sample]))
    if "check" in facets:
        probes.append(("check", ["check", sample]))
    for tag, argv in probes:
        r = subprocess.run([exe, *argv], cwd=_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(
                f"smoke test failed for {name} {tag} (exit {r.returncode}):\n"
                f"{r.stdout[-1200:]}\n{r.stderr[-1200:]}"
            )
        print(f"   smoke {tag}: OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="TransParadigm facet packaging pipeline")
    ap.add_argument("target", nargs="?", help="facets.json 中的切面名")
    ap.add_argument("--all", action="store_true", help="构建全部切面")
    ap.add_argument("--dry-run", action="store_true", help="只生成入口，不构建")
    args = ap.parse_args()

    spec = _load_spec()
    if args.all:
        # 跳过 "//" 注释键（JSON 无注释语法，facets.json 用 "//" 键承载说明；
        # 不过滤会把注释字符串当切面名传进 build → spec['facets'] 对 str 取下标）
        targets = [k for k in spec if not k.startswith("//")]
    elif args.target:
        if args.target not in spec or args.target.startswith("//"):
            sys.exit(f"unknown target {args.target!r}; available: {sorted(spec)}")
        targets = [args.target]
    else:
        ap.print_help()
        sys.exit(2)

    for name in targets:
        build(name, spec[name], dry_run=args.dry_run)


if __name__ == "__main__":
    main()
