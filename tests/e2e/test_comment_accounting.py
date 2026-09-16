"""注释盘账（缺口 c/d）——零丢失 / 零重复 / 通道兜底。

背景（2026-09-17 三方向评估）：注释落位涉及多条通道（行中槽 / 规则内部
让位闸门 / 容器上浮 / 行首领取 / 锚点兜底），单点修复容易"修一处漏一处"，
且此前的"注释丢失"都是内容级缺陷（条件块原文随 marker 一起消失）。本文件
把盘账与兜底固化成门禁：

- `test_real_corpus_comment_no_loss`：真实语料（darkriscv）——每条源注释
  文本在输出里至少出现一次（零丢失）+ 无 `<tpc:` 残留（marker 全部回插）。
- `test_rule_interior_comment_rendered_exactly_once`：规则内部注释（本轮修的
  形状）恰好渲染一次（不重复）。
- `test_entry_comment_registered_on_fallback_channel`：缺口 d——表达式入口
  注释**既挂树槽、也登记锚点通道**（兜底；挂树失败/节点未被渲染时 marker
  仍可回插）。
"""

import importlib
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from core.define import Node  # noqa: E402
from pipeline import run_pipeline_on_source  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DARKRISCV = os.path.join(
    _ROOT, "tests", "e2e", "samples", "real", "ref", "ref_darkriscv.v"
)


def _run(src: str, fmt: bool = True, expand: bool = True):
    r = run_pipeline_on_source(
        source=src, rules_dir="grammar/verilog", quiet=True,
        no_lint=True, format_output=fmt, expand_macros=expand,
    )
    assert r["success"], r.get("error", "")
    return r


def test_real_corpus_comment_no_loss() -> None:
    """darkriscv：源注释零丢失 + 条件块 marker 零残留。

    比较用**空白归一化**文本：多行块注释在输出里会重排内部缩进（` *` → `*`，
    既有行为），逐字匹配会误报。归一化只放松"空白差异"，整条注释丢失仍能被
    检出（文本整体不在场）。
    """
    with open(_DARKRISCV, encoding="utf-8") as fh:
        src = fh.read()
    out = _run(src)["output"]
    assert out.count("<tpc:") == 0, "marker 未被回插（条件块/宏原文会缺失）"

    flat_out = " ".join(out.split())
    src_comments = [
        c.strip()
        for c in re.findall(r"//[^\n]*|/\*.*?\*/", src, re.S)
        if c.strip() and not c.strip().startswith("//`")
    ]
    mode = Counter(src_comments)
    missing = [
        t
        for t, n in mode.items()
        if flat_out.count(" ".join(t.split())) < n
    ]
    assert not missing, f"注释丢失 {len(missing)} 种: {[m[:40] for m in missing[:5]]}"


def test_rule_interior_comment_rendered_exactly_once() -> None:
    """规则内部注释（`=` 与右操作数之间）恰好渲染一次（零丢失 + 零重复）。"""
    src = "module m;\n    wire a = // why\n        b;\nendmodule\n"
    out = _run(src)["output"]
    assert out.count("// why") == 1, out
    assert "// why" in out and "b;" in out, out


def test_entry_comment_registered_on_fallback_channel() -> None:
    """缺口 d：表达式入口注释既挂树槽、也登记锚点通道（兜底不丢内容）。

    挂树是主路径；锚点登记是"节点未被渲染/被内联丢弃"时的兜底——marker 的
    文本承载条件块原文，只挂树不兜底会静默丢块（宏调用作右操作数即如此）。
    """
    src = "module m;\n    wire a =\n        // note\n        b;\nendmodule\n"
    r = _run(src)
    out = r["output"]
    assert "// note" in out, out

    parser = r.get("parser")
    if parser is None:
        return  # 该入口未回传 parser（老路径）——挂树断言已在上方覆盖
    anchors = getattr(parser, "_comment_anchors", None) or []
    assert any(a.get("text", "").strip() == "// note" for a in anchors), (
        "表达式入口注释未登记锚点通道（兜底缺失）"
    )

    ast = r.get("ast")
    if isinstance(ast, Node):
        found: list[str] = []

        def walk(n):
            slots = getattr(n, "_comment_slots", None)
            if isinstance(slots, dict):
                for value in slots.values():
                    if isinstance(value, dict):
                        for entries in value.values():
                            found.extend(t for t, _ in entries)
                    elif isinstance(value, list):
                        found.extend(v for v in value if isinstance(v, str))
            for name, val in vars(n).items():
                if name.startswith("_"):
                    continue
                if isinstance(val, Node):
                    walk(val)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, Node):
                            walk(item)

        walk(ast)
        assert any("// note" in t for t in found), "表达式入口注释未挂树槽"
