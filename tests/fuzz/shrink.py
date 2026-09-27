"""shrink.py — finding 最小化 + 沉淀为 edge 语料（fuzz 回馈链路的后两步）。

链路全景（前两步在 `run_fuzz.py`）：

    生成/变异 ──► 跑不变量（oracle.py）──► findings/*.v + index.jsonl     ← 已有
                                          │
                    shrink.py --all ──────┘
                      ├─ ① 最小化：ddmin（行块 / 补集）+ 尾截，判据 = "仍触发同一**类别**"
                      └─ ② 沉淀：最小复现 + 溯源抬头 → edge 语料 clean/ 或 reject/
                                 （**拒绝**写未修复的样本：那会让门禁变红）

判据与不变量**同一来源**（`oracle.py`）：最小化若换一套判据，缩出来的就不是原来那个
bug 了——故两边都 import 同一模块。

算法参照（详见 `docs/references.md`「测试输入最小化与回归沉淀」）：
ddmin 出自 Zeller & Hildebrandt, *Simplifying and Isolating Failure-Inducing Input*
(IEEE TSE 2002)——按块删除 + 只保留块（补集）两路收缩，对"大部分内容与失败无关"
的输入效率远高于逐行删除。本实现取其中的**行**作单元（文本类输入的自然粒度；
语法感知的单元见 references 里 perses 一路的"未实现 + 原因"）。

用法：
    python tests/fuzz/shrink.py --all --pack grammar/verilog
    python tests/fuzz/shrink.py --file tests/fuzz/findings/00012_crash_gen.v --kind crash
    python tests/fuzz/shrink.py --all --sediment tests/edge/edge_corpus --cause "..."
    python tests/fuzz/shrink.py --file X.v --kind non-idempotent --out _drafts/min

Doc: tests/fuzz/README.md（回馈链路与纪律）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
for p in (_REPO, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from lexer import Lexer  # noqa: E402

import oracle  # noqa: E402

_INDEX_NAME = "index.jsonl"


# ── 判据（interestingness test）────────────────

class Predicate:
    """"这段输入是否仍触发同一**类别**的违反" —— ddmin 的判据。

    ⚠ 只比 `kind`，不比 `detail`：detail 里含计数（如 `in 12 → out 13 tokens`），
    会随收缩本身变化，逐字比对会让最小化一步都走不动。同一类别 = 同一失败模式，
    这是 delta debugging 的标准判据（Zeller TSE 2002）。
    结果按输入文本缓存：ddmin 的补集/删除两路会反复试同一候选，重复跑管线是纯浪费。
    """

    def __init__(self, lexer, *, pack: str, ext_dirs: list[str], kind: str,
                 label: str, max_tests: int = 2000, trace: bool = False,
                 require_parse: bool = False):
        self._lexer = lexer
        self._pack = pack
        self._ext_dirs = ext_dirs
        self._kind = kind
        self._label = label
        self._max_tests = max_tests
        self._trace = trace
        self._require_parse = require_parse
        self._cache: dict[str, bool] = {}
        self.tests = 0
        self.exhausted = False

    def __call__(self, src: str) -> bool:
        hit = self._cache.get(src)
        if hit is not None:
            return hit
        if self.tests >= self._max_tests:
            self.exhausted = True
            return False
        self.tests += 1
        ok = any(
            v.kind == self._kind
            for v in oracle.evaluate_format(
                src, self._lexer, rules_dir=self._pack,
                ext_dirs=self._ext_dirs, label=self._label,
            )
        )
        if ok and self._require_parse:
            # 语法有效性闸（perses 一路的思路：约束中间产物保持可解析）。
            # 默认关：纯文本缩减能多缩（实测会把 `int first` 并成 `intrst`——
            # 仍是同一个缺陷的最小核，但读起来不像程序）。开启后收缩幅度小、
            # 产物保持"像一段程序"，适合要把最小复现贴进文档/issue 的场合。
            ok = bool(oracle.format_source(src, self._pack, self._ext_dirs).get("success"))
        self._cache[src] = ok
        if self._trace:
            print(f"    test#{self.tests}: {'hit ' if ok else 'miss'} "
                  f"({len(src)}B)", file=sys.stderr)
        return ok


# ── ddmin ─────────────────────────────────────

def _split(items: list, n: int) -> list[list]:
    """把 items 均分成至多 n 块（块大小尽量相等，前几块多 1）。"""
    k = len(items)
    n = max(1, min(n, k))
    base, extra = divmod(k, n)
    chunks: list[list] = []
    i = 0
    for j in range(n):
        size = base + (1 if j < extra else 0)
        chunks.append(items[i:i + size])
        i += size
    return chunks


def ddmin(units: list, test, *, max_units: int | None = None) -> list:
    """Zeller ddmin：返回**仍满足 test** 的子集（1-minimal，受预算限制）。

    `units` 是有序单元（这里是行）；`max_units` 给出上界规模时先截断到该规模
    （找不到 interesting 前缀就原样返回——调用方另有尾截 pass 兜底）。
    """
    if not units:
        return list(units)
    cur = list(units)
    n = 2
    while len(cur) >= 2:
        chunks = _split(cur, n)
        progressed = False
        # ① 删除：去掉一块后仍 interesting → 采用
        for i in range(len(chunks)):
            cand = [u for j, ch in enumerate(chunks) if j != i for u in ch]
            if cand and test(cand):
                cur = cand
                n = max(n - 1, 2)
                progressed = True
                break
        if progressed:
            continue
        # ② 补集：只保留一块仍 interesting → 采用（收缩到"相关核心"的关键一步）
        if len(chunks) > 1:
            for ch in chunks:
                if len(ch) < len(cur) and test(list(ch)):
                    cur = list(ch)
                    n = max(n - 1, 2)
                    progressed = True
                    break
        if progressed:
            continue
        if n >= len(cur):
            break
        n = min(len(cur), 2 * n)
    return cur


# ── 各 pass ────────────────────────────────────

def _join_lines(lines: list[str], trailing_nl: bool) -> str:
    return "\n".join(lines) + ("\n" if trailing_nl else "")


def shrink_text(src: str, test, *, token_pass: bool = False) -> tuple[str, list[str]]:
    """行级 ddmin + 尾截 + 行内字符级（+ 可选 token 级）。返回 (最小文本, 步骤日志)。"""
    log: list[str] = []
    trailing_nl = src.endswith("\n")
    lines = src.split("\n")
    if trailing_nl and lines and lines[-1] == "":
        lines = lines[:-1]

    before = len(lines)
    lines = ddmin(lines, lambda ls: test(_join_lines(ls, trailing_nl)))
    if len(lines) != before:
        log.append(f"行级 ddmin: {before} → {len(lines)} 行")

    # 尾截：从尾部逐行丢（ddmin 在"尾部全是无关内容"时也能做到，但这一步是
    # 一次线性扫描、极便宜，且能修掉 ddmin 因粒度收敛停留的尾巴）
    trimmed = 0
    while len(lines) > 1 and test(_join_lines(lines[:-1], trailing_nl)):
        lines = lines[:-1]
        trimmed += 1
    if trimmed:
        log.append(f"尾截: -{trimmed} 行")

    # 首行去空：最小复现不留前导空行（不影响 interestingness 就丢）
    lead = 0
    while len(lines) > 1 and lines[0].strip() == "" and test(
        _join_lines(lines[1:], trailing_nl)
    ):
        lines = lines[1:]
        lead += 1
    if lead:
        log.append(f"去前导空行: -{lead} 行")

    lines, clog = _char_pass(lines, trailing_nl, test)
    log.extend(clog)

    text = _join_lines(lines, trailing_nl)
    if token_pass:
        text2, tlog = _token_pass(text, test)
        if text2 != text:
            text = text2
            log.extend(tlog)
    return text, log


def _char_pass(lines: list[str], trailing_nl: bool, test,
               max_line_len: int = 4000) -> tuple[list[str], list[str]]:
    """**行内**字符级 ddmin：逐行把该行内容按字符块删（其余行固定）。

    没有这一步，单行 finding 一行都缩不动（实测：C 包非幂等样本是 86 字节的
    **单行**，行级 ddmin 无事可做；真正能缩的是注释长度——**折行阈值**才是该缺陷
    最小复现的核心）。逐行跑而不是全文字符级：多行输入的行级 pass 已吃掉大头，
    全文字符级只会把判据预算烧在无关行上。
    """
    log: list[str] = []
    for _ in range(3):  # 行内收缩可能让别的行变得可缩——迭代到不动点（有界）
        changed = False
        for i, line in enumerate(lines):
            if len(line) < 2 or len(line) > max_line_len:
                continue

            def probe(chars: list[str], idx: int = i) -> bool:
                cand = list(lines)
                cand[idx] = "".join(chars)
                return test(_join_lines(cand, trailing_nl))

            new_line = "".join(ddmin(list(line), probe))
            if new_line != line:
                log.append(f"行 {i + 1} 内字符级: {len(line)} → {len(new_line)} 字符")
                lines = list(lines)
                lines[i] = new_line
                changed = True
        if not changed:
            break
    return lines, log


def _token_pass(text: str, test) -> tuple[str, list[str]]:
    """token 级收缩：按"空白切分后逐词删"（保留词内内容与顺序）。

    ⚠ 只做**词删除**，不做重排/重写：注释与空白是 finding 的一部分（注释回插类
    缺陷靠它们复现），重排会改掉现场。词删除在畸形输入上照样可跑（不要求可
    token 化），且比行级更细一档。
    """
    import re

    words = re.findall(r"\S+|\s+", text, flags=re.S)
    before = len(words)
    words = ddmin(words, lambda ws: test("".join(ws)))
    if len(words) == before:
        return text, []
    return "".join(words), [f"token 级 ddmin: {before} → {len(words)} 段"]


# ── 沉淀 ───────────────────────────────────────

def _header(kind: str, expect: str, *, cause: str | None, src_rec: dict | None,
            shrunk: str, original: str) -> str:
    """edge 语料抬头（与既有语料同格式，见 tests/edge/edge_corpus/*/*.v）。"""
    today = date.today().isoformat()
    verb = "成功" if expect == "clean" else "失败"
    cause_txt = cause if cause else "成因待补（--cause 补）"
    line1 = f"// edge {expect}（fuzz 回归 {today}）: {cause_txt}。"
    origin = ""
    if src_rec:
        origin = f"；原 finding {src_rec.get('file', '?')}"
    line2 = (
        f"// fuzz 类别 {kind}{origin}；最小复现 "
        f"{len(original)}→{len(shrunk)} 字节 / "
        f"{original.count(chr(10)) + 1}→{shrunk.count(chr(10)) + 1} 行；"
        f"修复后必须{verb}。"
    )
    return line1 + "\n" + line2 + "\n"


def sediment(text: str, *, pack: str, ext_dirs: list[str], kind: str,
             edge_root: str, name: str | None, cause: str | None,
             rec: dict | None, original: str, still_violates: bool,
             force: bool = False) -> tuple[bool, str]:
    """把最小复现写进 edge 语料。返回 (是否写入, 说明)。

    **两道闸**（缺一就不写）：
    1. 该**类别**的违反必须已不再复现（`still_violates`）——否则写进去是把未修的
       缺陷固化成"期望行为"（实测踩过：只按 `success` 判 clean/reject 时，非幂等
       样本 `success=True` 就被当成 clean 写进了 clean/，而它仍是活的缺陷）；
    2. 行为要能落进 clean/reject 二者之一（崩溃或静默失败 → 不落）。
    """
    if still_violates:
        return False, (f"类别 {kind} 仍在复现——**先修再沉淀**："
                       "写进去等于把未修缺陷固化成期望行为")
    expect = oracle.expectation_of(text, pack, ext_dirs)
    if expect == "unfixed":
        return False, ("样本崩溃或静默失败（既非 clean 也非 reject）——"
                       "**先修再沉淀**：写进去会让 edge 门禁变红")
    stem = name or f"fuzz_{kind.replace('-', '_')}_{_short_hash(text)}"
    if not stem.endswith(".v"):
        stem += ".v"
    target_dir = os.path.join(edge_root, expect)
    target = os.path.join(target_dir, stem)
    if os.path.exists(target) and not force:
        return False, f"目标已存在（--force 覆盖）：{target}"
    os.makedirs(target_dir, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(_header(kind, expect, cause=cause, src_rec=rec,
                        shrunk=text, original=original) + text)
    return True, target


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


# ── 输入收集 ───────────────────────────────────

def load_records(findings_dir: str) -> dict[str, dict]:
    """读 findings/index.jsonl → {文件名: 记录}（无索引返回空）。"""
    path = os.path.join(findings_dir, _INDEX_NAME)
    recs: dict[str, dict] = {}
    if not os.path.isfile(path):
        return recs
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if rec.get("file"):
                recs[rec["file"]] = rec
    return recs


def list_findings(findings_dir: str) -> list[str]:
    if not os.path.isdir(findings_dir):
        return []
    return sorted(
        os.path.join(findings_dir, n)
        for n in os.listdir(findings_dir)
        if n.endswith(".v")
    )


def infer_kind(src: str, lexer, *, pack: str, ext_dirs: list[str],
               label: str) -> str | None:
    """无索引时按 oracle 现测违反类别（多类时取第一条——只做兜底）。"""
    vs = oracle.evaluate_format(src, lexer, rules_dir=pack, ext_dirs=ext_dirs,
                                label=label)
    return vs[0].kind if vs else None


# ── 主流程 ─────────────────────────────────────

def shrink_one(path: str, *, pack: str, ext_dirs: list[str], lexer, kind: str | None,
               label: str, out_dir: str, token_pass: bool, max_tests: int,
               sediment_root: str | None, cause: str | None, name: str | None,
               rec: dict | None, force: bool, trace: bool,
               require_parse: bool = False) -> dict:
    """最小化一个 finding（+ 可选沉淀）。返回结果字典（含 `skipped` 表示跳过）。

    ⚠ **链路时序**（决定这里为什么分岔）：最小化只在缺陷**还活着**时做得动
    （判据 = "仍触发同一类别"）；而沉淀只在缺陷**已修**时才允许写（否则把未修
    缺陷固化成期望行为）。两者天然分处修复前后，故：
      · 仍复现 → 最小化 →（若带 --sediment）沉淀会被**拒**，提示先修；
      · 不复现 → 不再最小化，但**照常走沉淀**（这正是修完之后的那一遍）。
    早期版本没有第二条分岔，结果是"带 --sediment 永远沉淀不了"（活的被拒、
    修完的又被当"已修"跳过）。
    """
    with open(path, encoding="utf-8") as f:
        original = f.read()
    if kind is None:
        kind = infer_kind(original, lexer, pack=pack, ext_dirs=ext_dirs, label=label)
        if kind is None:
            return {"file": path,
                    "skipped": "无索引且当前代码下无任何违反（可能已修）"}
    pred = Predicate(lexer, pack=pack, ext_dirs=ext_dirs, kind=kind, label=label,
                     max_tests=max_tests, trace=trace, require_parse=require_parse)
    reproduces = pred(original)
    if not reproduces:
        if not sediment_root:
            return {"file": path, "kind": kind,
                    "skipped": f"类别 {kind} 已不复现（已修）；带 --sediment 可走沉淀"}
        ok, info = sediment(original, pack=pack, ext_dirs=ext_dirs, kind=kind,
                            edge_root=sediment_root, name=name, cause=cause,
                            rec=rec, original=original, still_violates=False,
                            force=force)
        return {
            "file": path, "kind": kind, "out": None, "minimized": False,
            "before_bytes": len(original), "after_bytes": len(original),
            "before_lines": original.count("\n") + 1,
            "after_lines": original.count("\n") + 1,
            "tests": pred.tests, "exhausted": False,
            "steps": ["已修（该类别不复现）→ 未最小化，直接沉淀"],
            "sedimented": ok, "sediment_info": info,
        }

    shrunk, log = shrink_text(original, pred, token_pass=token_pass)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(path))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(shrunk)
    result = {
        "file": path, "kind": kind, "out": out_path, "minimized": True,
        "before_bytes": len(original), "after_bytes": len(shrunk),
        "before_lines": original.count("\n") + 1,
        "after_lines": shrunk.count("\n") + 1,
        "tests": pred.tests, "exhausted": pred.exhausted, "steps": log,
    }
    if sediment_root:
        ok, info = sediment(shrunk, pack=pack, ext_dirs=ext_dirs, kind=kind,
                            edge_root=sediment_root, name=name, cause=cause,
                            rec=rec, original=original,
                            still_violates=pred(shrunk), force=force)
        result["sedimented"] = ok
        result["sediment_info"] = info
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="finding 最小化 + 沉淀（fuzz 链路后两步）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--all", action="store_true", help="处理 findings 目录下全部 .v")
    src.add_argument("--file", help="处理单个 finding")
    ap.add_argument("--pack", "--rules-dir", dest="pack", default="grammar/verilog")
    ap.add_argument("--findings-dir", default=os.path.join(_HERE, "findings"))
    ap.add_argument("--out", default=os.path.join(_HERE, "findings", "min"),
                    help="最小复现输出目录（默认 findings/min/）")
    ap.add_argument("--kind", default=None,
                    help="目标违反类别（缺省：按索引，或现测第一条）")
    ap.add_argument("--label", default="gen",
                    help="token 保序判据适用性（gen / mut:<file>；缺省 gen = 最严）")
    ap.add_argument("--token-pass", action="store_true", help="追加 token 级收缩")
    ap.add_argument("--max-tests", type=int, default=2000,
                    help="判据调用上限（每次 = 一次管线全跑；到顶按 partial 报）")
    ap.add_argument("--sediment", metavar="EDGE_DIR", default=None,
                    help="沉淀目标 edge 语料根目录（如 tests/edge/edge_corpus）")
    ap.add_argument("--cause", default=None, help="沉淀抬头的成因句（人写）")
    ap.add_argument("--name", default=None, help="沉淀文件名（默认 fuzz_<kind>_<hash>.v）")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的沉淀文件")
    ap.add_argument("--require-parse", action="store_true",
                    help="判据加一道语法有效性闸（候选必须仍可解析）——收缩幅度小、"
                         "产物更像程序；默认关")
    ap.add_argument("--trace", action="store_true", help="每次判据调用打到 stderr")
    args = ap.parse_args()

    ext_dirs = oracle.ext_dirs_for(args.pack)
    lexer = Lexer(rules_dir=args.pack, ext_dirs=ext_dirs)
    recs = load_records(args.findings_dir)

    if args.file:
        targets = [args.file]
    else:
        targets = list_findings(args.findings_dir)
        if not targets:
            print(f"没有 finding（{args.findings_dir}）；先跑 run_fuzz.py")
            sys.exit(2)

    n_min = n_sed = n_skip = 0
    for path in targets:
        name = os.path.basename(path)
        rec = recs.get(name)
        r = shrink_one(
            path, pack=args.pack, ext_dirs=ext_dirs, lexer=lexer,
            kind=args.kind or (rec or {}).get("kind"),
            label=args.label or (rec or {}).get("label", "gen"),
            out_dir=args.out, token_pass=args.token_pass,
            max_tests=args.max_tests, sediment_root=args.sediment,
            cause=args.cause, name=args.name, rec=rec, force=args.force,
            trace=args.trace, require_parse=args.require_parse,
        )
        if r.get("skipped"):
            n_skip += 1
            print(f"—  {name}: 跳过（{r['skipped']}）")
            continue
        n_min += 0 if not r.get("minimized", True) else 1
        flag = "partial（预算到顶）" if r["exhausted"] else "1-minimal"
        title = "✓  " if r.get("minimized", True) else "·  "
        print(f"{title}{name}  [{r['kind']}]  {r['before_bytes']}→{r['after_bytes']} 字节 / "
              f"{r['before_lines']}→{r['after_lines']} 行  "
              f"（判据 {r['tests']} 次"
              + (f"，{flag}" if r.get("minimized", True) else "，未最小化") + "）")
        for step in r["steps"]:
            print(f"     · {step}")
        if r.get("out"):
            print(f"     → {r['out']}")
        if "sedimented" in r:
            if r["sedimented"]:
                n_sed += 1
                print(f"     ✓ 已沉淀：{r['sediment_info']}")
            else:
                print(f"     ✗ 未沉淀：{r['sediment_info']}")

    print(f"\n最小化 {n_min} / 沉淀 {n_sed} / 跳过 {n_skip}")
    if args.sediment and n_sed:
        print("下一步：python tests/edge/run_edge.py"
              + (f" --corpus {args.sediment}" if args.sediment else "")
              + "   # 复核门禁；并把 README 的 bug 表补一行")


if __name__ == "__main__":
    main()
