"""tools/dump_pipeline_state.py — 管线语言状态转储（诊断"跨语言串味"）。

Doc: tests/README.md（隔离与顺序巡检·进程级隔离一节）

用途：打印当前进程里管线视角的语言状态——`_PIPELINE_SHARED` 的缓存键、每个条目
里缓存的 rules 条数 / mapping_cfg / schedules / render_handler、`ConfigRegistry`
的当前语言（`_entries_source`）、已装载组件。它回答两个问题：

1. 跑完语言 A 之后，语言 B 的共享条目里装的是**谁**的组件与规则；
2. `--pre` 复现"同进程先跑过别的语言"的场景，看 B 的输出是否被串味。

实测背景（2026-09-14，修复提交 e57df37）：同进程「先跑 c4 管线 → 再跑 verilog」
时 verilog 输出为空、`ast=AsmProgram`。根因是语言作用域状态跨语言累积（规则注册表
夺根 / 插件注册表被别的语言引用 / 共享条目建立时配置停在别的语言）。本工具是那次
定位的现场转储器，也用于回归时"看一眼状态"。

用法：
    python tools/dump_pipeline_state.py                    # 只跑 verilog 宏往返
    python tools/dump_pipeline_state.py --pre grammar/c4   # 先跑 c4（复现串味场景）
    python tools/dump_pipeline_state.py --source <file.v>  # 指定 verilog 输入
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from tests import _bootstrap  # noqa: E402,F401  # pyright: ignore[reportUnusedImport] — 副作用导入（sys.path + stdout UTF-8）
from pipeline import _PIPELINE_SHARED, run_pipeline_on_source  # noqa: E402
from core.config_registry import ConfigRegistry  # noqa: E402
from core import plugin_loader  # noqa: E402

_DEFAULT_VERILOG = "tests/e2e/samples/macro/ref/ref_pp_func_macro_stmt.v"
_C4_SRC = "int main() { int x; x = 1; return x; }"


def _quiet(fn, *args, **kwargs):
    """跑管线并吞掉其日志（本工具只关心状态与结果）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


def _strip_all(text: str) -> str:
    """去行注释与全部空白（与 e2e 保真度判定一致）。"""
    lines = []
    for line in text.splitlines():
        ci = line.find("//")
        lines.append(line[:ci] if ci >= 0 else line)
    return "".join("".join(lines).split())


def _dump_entries() -> None:
    """打印共享条目与语言状态。"""
    print(f"  _PIPELINE_SHARED 键: {list(_PIPELINE_SHARED)}")
    print(f"  _entries_source: {ConfigRegistry._entries_source}")
    print(f"  已装载组件: {sorted(plugin_loader._loaded_components)}")
    for key, entry in _PIPELINE_SHARED.items():
        rules = entry.get("rules") or {}
        print(f"  ── 条目 {key[0]}（ext_dirs={key[1]}）")
        print(f"     rules 条数: {len(rules)}")
        print(f"     schedules: {list(entry.get('schedules') or [])}")
        print(f"     mapping_cfg 键: {sorted(entry.get('mapping_cfg') or {})}")
        print(f"     render_handler: {entry.get('render_handler')}")
        print(f"     renderer/lexer: {type(entry.get('renderer')).__name__}"
              f"/{type(entry.get('lexer')).__name__}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dump_pipeline_state",
        description="管线语言状态转储（诊断跨语言串味）",
    )
    ap.add_argument("--pre", default=None,
                    help="先跑一次该语言包（复现\"同进程先跑过别的语言\"，如 grammar/c4）")
    ap.add_argument("--lang", default=None, help="随后跑的语言包（默认 verilog）")
    ap.add_argument("--source", default=None, help="随后跑用的 verilog 输入文件")
    args = ap.parse_args(argv)

    if args.pre:
        res = _quiet(run_pipeline_on_source, source=_C4_SRC, quiet=True, rules_dir=args.pre)
        print(f"[pre] {args.pre}: success={res.get('success')} "
              f"输出={len(res.get('output') or '')} 字")
        _dump_entries()
        print()

    src_path = args.source or _DEFAULT_VERILOG
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    kw = {"rules_dir": args.lang} if args.lang else {}
    res = _quiet(run_pipeline_on_source, source=src, quiet=True, expand_macros=True,
                 no_lint=True, **kw)
    out = res.get("output") or ""
    ratio = difflib.SequenceMatcher(None, _strip_all(src), _strip_all(out)).ratio()
    print(f"[main] {args.lang or 'grammar/verilog'} 宏往返: success={res.get('success')} "
          f"输出={len(out)} 字 保真度={ratio:.4f} ast={getattr(res.get('ast'), 'node_name', None)}")
    print(f"        error={res.get('error')!r}")
    _dump_entries()
    return 0 if res.get("success") and out else 1


if __name__ == "__main__":
    sys.exit(main())
