"""config_sites.py — 配置同步点位枚举器（引擎语义变更 → 语言包配置同步）。

动机：引擎语义/键名一改（如换行三态化），"哪些语言包配置点要跟着改"当前
只能逐个 TOML 人工翻——改动面不确定、易漏、且旧的错键会静默留着。本工具把
这个过程机械化为"翻译"四步：

  1. 找语言包：`grammar/*/tpc.toml`（+ 其下组件目录的 tpc.toml）
  2. 加载并扫描 TOML 文本：跟踪 `[段]` 路径与行内表 `{k = v}`，记录每个键的
     `file:line` / 段路径 / 原值
  3. 关键字匹配按**整键相等**比对——`break` 不命中 `break_distance`，
     `soft` 不命中 `first_soft` / `no_soft`（子串误伤是这类改写的主要坑）
  4. 逐项替换只改键 token 本身（值/注释/排版不动），默认 dry-run

用法：
  python tools/config_sites.py list                      # 全量点位（按键聚合）
  python tools/config_sites.py list --key break          # 单键点位（含 file:line）
  python tools/config_sites.py list --renderer-only      # 只看渲染布局段
  python tools/config_sites.py check                     # 渲染段里的"非引擎词汇"键
  python tools/config_sites.py rename --from break --to break_parent \\
      --value true [--renderer-only] [--apply]

`check` 是门禁式用法：引擎词汇表以外的键 = 拼错/过时/已删机制的残留配置。

Doc: policy/engine_config_sync.md（引擎语义变更的配置同步规程）
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 引擎词汇表（渲染布局段） ──────────────────────────────────────────
# 来源：原语注册表（运行时读，见 _engine_vocab）+ 原语 expr/元素取键汇总
# （`grep '\.get("' renderer/primitives/*.py`，2026-09-17）。改引擎键名时
# 先同步这里，再跑 `rename` 同步语言包。
_VOCAB_DISPATCH = (
    "text",
    "ref",
    "join",
    "group",
    "line",
    "indent",
    "opt",
    "soft_break",
    "align",
    "fill",
    "line_suffix",
    "intent",
    "suffix_when",
)
_VOCAB_ELEMENT = (
    "soft",
    "break",  # line 元素键：{soft = true} / {break = true}
    "nest",
    "items",
    "sep",
    "doc",
    "attr",
    "startswith",
    "inline_after",
    "first_soft",
    "no_soft",
    "prefix",
    "suffix",
)
_VOCAB_SECTION = (
    "layout",  # <Rule>.renderer.{layout,head,body,tail}
    "head",
    "body",
    "tail",
    "enabled",
    "role",
    "override",
    "indent",
    "break",
    "tail_break",
    "source",
    "text",
    "matcher",
    "break_distance",
    "min_group_size",
    "max_span",
    "max_width",
    "first_token",
    "family",
    "kind",
    "handler",
    "category",
)

# `override` 段的子键是**规则名**（`override.<ChildRule> = {...}`，见
# renderer/renderer.py::_get_merged_layout），不是引擎键——由结构位置豁免。
_STRUCTURAL_KEY_SECTIONS = (".override",)

_SECTION_RE = re.compile(r"^\s*(\[\[?)([^\]]+?)\]\]?\s*(?:#.*)?$")
_KEY_RE = re.compile(r"""(?<![\w.\-"'#])([A-Za-z_][\w\-]*)\s*=""")
_RENDERER_SUFFIX = ".renderer"


def _engine_vocab() -> set[str]:
    """引擎词汇表（渲染段）= 原语注册表 ∪ 元素键 ∪ 段字段键。"""
    return (
        set(_VOCAB_DISPATCH)
        | set(_dispatch_order())
        | set(_VOCAB_ELEMENT)
        | set(_VOCAB_SECTION)
    )


def _dispatch_order() -> tuple[str, ...]:
    """原语 dispatch 键及注册顺序（表达式求值按序取首个命中）。"""
    try:
        from renderer.primitives import get_registry

        keys = tuple(k for k, _ in get_registry())
        return keys or _VOCAB_DISPATCH
    except Exception:  # noqa: BLE001 — 工具可在最小环境跑（退化为声明顺序）
        return _VOCAB_DISPATCH


def _strip_comment(line: str) -> str:
    """去 TOML 行尾注释（引号内的 `#` 不算）。"""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _value_head(after: str) -> str:
    """取等号后值的头部（标量整值 / 容器首字符），用于点位核对与过滤。"""
    after = after.strip()
    if not after:
        return ""
    if after[0] in "{[":
        return after[0]
    if after[0] in "\"'":
        q = after[0]
        end = after.find(q, 1)
        return after[: end + 1] if end > 0 else after
    return after.split()[0].rstrip(",")


class Site(dict):
    """一个配置键点位：file/line/section/key/value/col（键 token 起止列）。"""


def _scan_file(path: str, rel: str) -> list[Site]:
    """扫描一个 TOML：记录每个键的 file:line/段路径/原值/所属行内表/消费方。

    `owner` = 该键所在行内表的**消费方键**：`=\u00a0{...}` 是其值（如 `opt`），
    数组元素则继承数组 owner（如 `line` / `group`）。用于区分：
      - owner == "line" → 元素由 `eval_line` **内联**处理（`soft`/`break` 不走
        dispatch，不会与其他原语键抢位）
      - 其余 → 走 `eval_expr` 按注册顺序 dispatch（多键同层会静默失效一个）
    """
    section = ""
    sites: list[Site] = []
    stack: list[tuple[int, int]] = []          # 打开的 `{`
    arrays: list[tuple[str, int]] = []         # 打开的 `[`（owner 键）
    table_owner: dict[tuple[int, int], str] = {}  # `{` 位置 → 消费方键
    table_parent: dict[tuple[int, int], tuple[int, int] | None] = {}  # 嵌套父表
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f.read().split("\n"), 1):
            m = _SECTION_RE.match(raw)
            if m:
                section = m.group(2).strip()
                stack, arrays = [], []
                continue
            code = _strip_comment(raw)
            last_key = ""
            prev_sig = ""
            quote = ""
            i = 0
            while i < len(code):
                ch = code[i]
                if quote:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == quote:
                        quote = ""
                    i += 1
                    continue
                if ch in "\"'":
                    quote = ch
                elif ch in "[{":
                    if prev_sig == "=":
                        owner = last_key
                    elif arrays:
                        owner = arrays[-1][0]
                    else:
                        owner = ""
                    if ch == "[":
                        arrays.append((owner, i))
                    else:
                        stack.append((lineno, i))
                        table_owner[(lineno, i)] = owner
                        table_parent[(lineno, i)] = stack[-2] if len(stack) > 1 else None
                elif ch == "]" and arrays:
                    arrays.pop()
                elif ch == "}" and stack:
                    stack.pop()
                elif ch.isalpha() or ch == "_":
                    j = i
                    while j < len(code) and (code[j].isalnum() or code[j] in "_-"):
                        j += 1
                    after = code[j:].lstrip()
                    if after.startswith("="):
                        key = code[i:j]
                        last_key = key
                        # 就地登记：所属表 = 当时最内层开着的 `{`（跨行安全）
                        top = stack[-1] if stack else None
                        sites.append(
                            Site(
                                file=rel,
                                line=lineno,
                                section=section,
                                key=key,
                                value=_value_head(after[1:]),
                                col=i,
                                end=j,
                                raw=raw,
                                table=f"{top[0]}:{top[1]}" if top else "",
                                owner=(
                                    table_owner.get(top, "") if top else ""
                                ),
                                parent=(
                                    f"{table_parent[top][0]}:{table_parent[top][1]}"
                                    if top and table_parent.get(top)
                                    else ""
                                ),
                            )
                        )
                    i = j - 1
                if not ch.isspace():
                    prev_sig = ch
                i += 1
    return sites


def _iter_toml(root: str, start: str) -> Iterable[tuple[str, str]]:
    for base, dirs, files in os.walk(start):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for name in sorted(files):
            if name.endswith(".toml"):
                full = os.path.join(base, name)
                yield full, os.path.relpath(full, root).replace("\\", "/")


def _packs(root: str, roots: list[str]) -> list[str]:
    if roots:
        return roots
    base = os.path.join(root, "grammar")
    if not os.path.isdir(base):
        return []
    return [
        os.path.join(base, d)
        for d in sorted(os.listdir(base))
        if os.path.isfile(os.path.join(base, d, "tpc.toml"))
    ]


def _collect(root: str, roots: list[str], renderer_only: bool) -> list[Site]:
    sites: list[Site] = []
    for pack in _packs(root, roots):
        for full, rel in _iter_toml(root, pack):
            for s in _scan_file(full, rel):
                if renderer_only and _RENDERER_SUFFIX not in s["section"]:
                    continue
                sites.append(s)
    return sites


# ── 模式实现 ────────────────────────────────────────────────────────


def cmd_list(args: argparse.Namespace) -> int:
    sites = _collect(args.root, args.pack, args.renderer_only)
    if args.key:
        sites = [s for s in sites if s["key"] == args.key]
    if args.value:
        sites = [s for s in sites if s["value"] == args.value]
    by_key: dict[str, list[Site]] = {}
    for s in sites:
        by_key.setdefault(s["key"], []).append(s)
    print(f"点位合计: {len(sites)}（语言包 {len(_packs(args.root, args.pack))} 个）")
    vocab = _engine_vocab()
    for key in sorted(by_key, key=lambda k: (-len(by_key[k]), k)):
        hits = by_key[key]
        flag = "" if key in vocab else "  ← 非引擎词汇"
        print(f"\n[{key}] {len(hits)} 处{flag}")
        for s in hits:
            print(f"  {s['file']}:{s['line']}  {{{s['section']}}}  = {s['value']}")
    return 0


def _is_structural(site: Site) -> bool:
    """结构键（非引擎词汇）：`override` 下的规则名、容器键（值为 `{`）。"""
    if any(mark in site["section"] for mark in _STRUCTURAL_KEY_SECTIONS):
        return True
    return site["value"] == "{"


def _multi_dispatch_tables(sites: list[Site]) -> list[tuple[str, int, list[str], int]]:
    """同一行内表里多个**原语 dispatch 键** → 只有注册顺序最前的生效。

    表达式求值按注册顺序取首个命中的键（见 renderer/primitives/__init__.py
    ::eval_expr）。一个 dict 同时写 `group` 与 `ref` 时，`ref`（注册序 0）
    抢先，`group` 及其内部的 `break`/`soft` **静默失效**（看着改了其实没生效）
    ——阴影沿嵌套表传递。
    返回 [(file, 首行, 生效/失效键, 失效子树内的键数)]。
    """
    order = {k: i for i, k in enumerate(_dispatch_order())}
    tables: dict[tuple[str, str], list[Site]] = {}
    tparent: dict[tuple[str, str], str] = {}
    for s in sites:
        if s["table"]:
            tparent.setdefault((s["file"], s["table"]), s["parent"])
        # `line` 数组元素由 eval_line 内联处理（不走 dispatch）→ 不参与本检查
        if s["owner"] == "line" or not s["table"] or s["key"] not in order:
            continue
        tables.setdefault((s["file"], s["table"]), []).append(s)

    shadowed: list[tuple[str, str, list[str]]] = []
    for (f, tid), group in tables.items():
        keys = sorted({g["key"] for g in group}, key=lambda k: order[k])
        if len(keys) > 1:
            shadowed.append((f, tid, keys))
    dead_ids = {f"{f}:{tid}" for f, tid, _ in shadowed}

    def _in_dead(file: str, table: str) -> bool:
        seen: set[str] = set()
        cur = table
        while cur and cur not in seen:
            seen.add(cur)
            if f"{file}:{cur}" in dead_ids:
                return True
            cur = tparent.get((file, cur), "")
        return False

    out: list[tuple[str, int, list[str], list[str]]] = []
    for f, tid, keys in shadowed:
        # 只报**最外层**被遮蔽表（嵌套被遮蔽表归并于其祖先，避免重复计数）
        p = tparent.get((f, tid), "")
        while p:
            if f"{f}:{p}" in dead_ids:
                break
            p = tparent.get((f, p), "")
        if p:
            continue
        line = min(s["line"] for s in sites if s["file"] == f and s["table"] == tid)

        def _under(file: str, table: str) -> bool:
            """该键所在表是否在本被遮蔽表的子树内（含自身）。"""
            seen: set[str] = set()
            cur = table
            while cur and cur not in seen:
                if file == f and cur == tid:
                    return True
                seen.add(cur)
                cur = tparent.get((file, cur), "")
            return False

        dead_keys = sorted(
            {
                f"{s['key']}@{s['line']}"
                for s in sites
                if _under(s["file"], s["table"])
                and (s["table"] != tid or s["key"] in keys[1:])
            }
        )
        out.append((f, line, keys, dead_keys))
    return out


def cmd_check(args: argparse.Namespace) -> int:
    vocab = _engine_vocab()
    sites = _collect(args.root, args.pack, renderer_only=True)
    unknown = [
        s for s in sites
        if s["key"] not in vocab and not _is_structural(s)
    ]
    structural = [s for s in sites if _is_structural(s) and s["key"] not in vocab]
    print(
        f"渲染段点位 {len(sites)} 处；非引擎词汇 {len(unknown)} 处"
        f"（另 {len(structural)} 处结构键已豁免）"
    )
    for s in unknown:
        print(f"  {s['file']}:{s['line']}  {{{s['section']}}}  {s['key']} = {s['value']}")
    shadowed = _multi_dispatch_tables(sites)
    print(f"多原语键同层（后者静默失效）{len(shadowed)} 处")
    for f, line, keys, dead_keys in shadowed:
        print(
            f"  {f}:L{line}  生效={keys[0]}  失效={', '.join(keys[1:])}"
            f"  失效子树键={', '.join(dead_keys) or '（无）'}"
        )
    if unknown:
        print("\n[FAIL] 渲染段存在引擎词汇表以外的键（拼写/过时/残留）")
        return 1
    print("[PASS] 渲染段键全在引擎词汇表内（结构键已剔除）")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    sites = _collect(args.root, args.pack, args.renderer_only)
    hits = [
        s for s in sites
        if s["key"] == args.frm and (args.value is None or s["value"] == args.value)
    ]
    if not hits:
        print("无匹配点位（整键相等比对，子串不命中）")
        return 0
    by_file: dict[str, list[Site]] = {}
    for s in hits:
        by_file.setdefault(s["file"], []).append(s)
    changed = 0
    for rel, group in sorted(by_file.items()):
        full = os.path.join(args.root, rel)
        lines = open(full, encoding="utf-8").read().split("\n")
        for s in group:
            i = s["line"] - 1
            line = lines[i]
            lines[i] = line[: s["col"]] + args.to + line[s["end"] :]
            print(f"{rel}:{s['line']}  - {s['raw']}")
            print(f"{rel}:{s['line']}  + {lines[i]}")
            changed += 1
        if args.apply:
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines))
    print(f"\n{'已写入' if args.apply else 'dry-run（未写入，加 --apply 生效）'}: {changed} 处")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="配置同步点位枚举器")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--root", default=_ROOT,
                        help="扫描根（默认项目根；测试/对拍另一检出时指定）")
        sp.add_argument("--pack", action="append", default=[],
                        help="语言包目录（默认 <root>/grammar/*/ 全部）")
        sp.add_argument("--renderer-only", action="store_true",
                        help="只看 <Rule>.renderer 段")

    lp = sub.add_parser("list", help="点位清单")
    add_common(lp)
    lp.add_argument("--key", help="按整键过滤（子串不命中）")
    lp.add_argument("--value", help="按值头部过滤（如 true / { / [）")
    lp.set_defaults(func=cmd_list)

    cp = sub.add_parser("check", help="渲染段非引擎词汇键（门禁式）")
    add_common(cp)
    cp.set_defaults(func=cmd_check)

    rp = sub.add_parser("rename", help="机械重命名键（默认 dry-run）")
    add_common(rp)
    rp.add_argument("--from", dest="frm", required=True, help="旧键（整键）")
    rp.add_argument("--to", required=True, help="新键")
    rp.add_argument("--value", help="只改该值的点位（如 true）")
    rp.add_argument("--apply", action="store_true", help="实际写入")
    rp.set_defaults(func=cmd_rename)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
