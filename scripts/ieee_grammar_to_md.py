"""ieee_grammar_to_md.py — 把 IEEE 1364-2005 PDF 的语法章节一次性转为 Markdown。

背景：linter/parser 维护需要频繁核对标准 BNF，每次用 PDF 库解析 590 页太慢。
本脚本把目标章节（默认 Annex A 正式文法）提取为 Markdown 缓存到 docs/，
之后直接读 MD / grep，不再碰 PDF。

用法:
    python scripts/ieee_grammar_to_md.py                       # 默认 Annex A → docs/ieee1364_2005_annex_a.md
    python scripts/ieee_grammar_to_md.py --out docs/other.md   # 自定义输出
    python scripts/ieee_grammar_to_md.py --start 517 --end 539 # 指定 1-based 页范围（跳过自动探测）

依赖: pypdf (pip install pypdf)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PDF = _ROOT / "grammar" / "verilog" / "IEEE_Std_1364_2005_IEEE_Standard_for_Ver.pdf"
_DEFAULT_OUT = _ROOT / "docs" / "ieee1364_2005_annex_a.md"

# 页眉/页脚/授权水印（pypdf 提取产物），整行剔除
_FURNITURE_RE = re.compile(
    r"^(?:"
    r"IEEE\s*"
    r"|.*IEEE STANDARD FOR VERILOG.*"
    r"|.*IEEE HARDWARE DESCRIPTION LANGUAGE.*"
    r"|.*HARDWARE DESCRIPTION LANGUAGE.*"
    r"|.*Copyright .* 2006 IEEE.*"
    r"|.*All rights reserved.*"
    r"|.*Authorized licensed use limited.*"
    r"|.*Restrictions apply.*"
    r")$"
)
_PAGE_NO_RE = re.compile(r"^\d{1,4}$")

# 章节标题（如 "A.8.7 Numbers" / "A.6.7 Case statements"）
_SECTION_RE = re.compile(r"^A\.\d+(\.\d+)*\s+\S.+$")


def _clean_page(text: str) -> list[str]:
    """剔除页眉页脚水印、纯页码行，保留语法正文行。"""
    out: list[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if _FURNITURE_RE.match(s):
            continue
        if _PAGE_NO_RE.match(s):
            continue
        out.append(s)
    return out


def _page_joined(reader: PdfReader, idx: int) -> str:
    """整页前几行文本（空格连接），用于附录标题页匹配。

    只取前 ~12 行：附录标题页（"Annex A (normative)"）的标记集中在此，
    而目录页虽然全文含 "Annex A"/"normative"，但首屏是页码列表，可避开。
    """
    lines = (reader.pages[idx].extract_text() or "").split("\n")
    return " ".join(x.strip() for x in lines[:12])


def _find_annex_range(reader: PdfReader, start_marker: str, end_marker: str) -> tuple[int, int]:
    """按 '名字+(normative)' 定位附录首末页（0-based 闭区间）。

    返回 (start_idx, end_idx)，start 是 end_marker 标题页的前一页，
    确保把整个附录正文（不含下一个附录标题页）纳入。
    """
    a = b = None
    for i in range(len(reader.pages)):
        joined = _page_joined(reader, i)
        if a is None and start_marker in joined and "normative" in joined:
            a = i
        elif a is not None and end_marker in joined and "normative" in joined:
            b = i
            break
    if a is None or b is None:
        raise RuntimeError(f"附录定位失败: {start_marker=} {end_marker=}")
    return a, b - 1


def convert(
    reader: PdfReader,
    start_idx: int,
    end_idx: int,
    title: str = "IEEE 1364-2005 — 语法章节（由 PDF 一次性提取，供快速查阅）",
    source: str = "`grammar/verilog/IEEE_Std_1364_2005_IEEE_Standard_for_Ver.pdf`",
) -> str:
    """提取 [start_idx, end_idx] 页为 Markdown：章节标题成 H2，正文成 ```text 块。"""
    md: list[str] = []
    md.append(f"# {title}")
    md.append("")
    md.append(f"> 来源: {source}")
    md.append("> 生成: `scripts/ieee_grammar_to_md.py`（改 PDF 后重跑即可刷新）")
    md.append("> 注: pypdf 文本提取对上下标/换行有噪声（如 `real_number\\n2 ::=`），以原文 PDF 为准。")
    md.append("")

    block: list[str] = []
    in_code = False

    def flush() -> None:
        nonlocal block, in_code
        if block:
            if not in_code:
                md.append("```text")
                in_code = True
            md.extend(block)
            block = []
        if in_code:
            md.append("```")
            in_code = False
        md.append("")

    for idx in range(start_idx, end_idx + 1):
        lines = _clean_page(reader.pages[idx].extract_text() or "")
        for ln in lines:
            if _SECTION_RE.match(ln):
                flush()
                md.append(f"## {ln}")
                md.append("")
                in_code = False
            else:
                block.append(ln)
    flush()
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", default=str(_DEFAULT_PDF))
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    ap.add_argument("--start", type=int, help="起始页（1-based），缺省自动探测 Annex A")
    ap.add_argument("--end", type=int, help="结束页（1-based），缺省自动探测 Annex A 末页")
    ap.add_argument("--start-marker", default="Annex A")
    ap.add_argument("--end-marker", default="Annex B")
    ap.add_argument("--title", default="IEEE 1364-2005 — 语法章节（由 PDF 一次性提取，供快速查阅）")
    ap.add_argument("--source", default="`grammar/verilog/IEEE_Std_1364_2005_IEEE_Standard_for_Ver.pdf`")
    args = ap.parse_args()

    reader = PdfReader(args.pdf)
    if args.start and args.end:
        start_idx, end_idx = args.start - 1, args.end - 1
    else:
        start_idx, end_idx = _find_annex_range(reader, args.start_marker, args.end_marker)

    md = convert(reader, start_idx, end_idx, title=args.title, source=args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"已写出 {out}（PDF 页 {start_idx + 1}-{end_idx + 1}，{len(md.splitlines())} 行）")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
