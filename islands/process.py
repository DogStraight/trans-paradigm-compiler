"""process.py — 岛文本 → 真实管线 → 片段文本（含后验）。

岛内一律走现有管线，不另造近似规则（片段模式契约）。P1 默认管线面 = format 等价：
parse + render + formatter 插件；analyze/transform 关闭（岛缺乏岛外上下文，语义级变换
须显式开启且另有判据，见 gap 档 P2）。

后验默认开且无跳过开关：
1. 管线成功（parse 未截断）；
2. 输出**再次**过管线成功；
3. 二次输出与一次输出**逐字相同**（双跑幂等）。

任何一步失败 ⇒ 该岛按 water 处理（调用方原样保留），不报错、不落编辑。
"""

from __future__ import annotations

import contextlib
import io

from pipeline import run_pipeline_on_source


def _run(source: str, rules_dir: str, ext_dirs: list[str] | None) -> dict:
    """跑一次岛管线；stderr/stdout 静默（岛试解析失败是常态，不污染用户输出）。"""
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        return run_pipeline_on_source(
            source=source,
            quiet=True,
            expand_macros=False,   # 岛内宏区间已由 water 判据跳过；此处不展开
            parse_enabled=True,
            no_lint=True,          # 岛有效性由 parser 判（lint 是启发式近似，不用于闸门）
            analyzer_enabled=False,
            transform_enabled=False,
            renderer_enabled=True,
            format_output=True,
            check_idempotent=False,  # 后验由本模块显式做（重解析 + 双跑逐字幂等）
            rules_dir=rules_dir,
            ext_dirs=ext_dirs,
        )


def format_island(
    island_text: str, rules_dir: str, ext_dirs: list[str] | None = None
) -> str | None:
    """岛文本 → 管线输出；后验不过返回 None（调用方按 water 原样保留）。"""
    if not island_text.strip():
        return None
    try:
        first = _run(island_text, rules_dir, ext_dirs)
    except Exception:  # noqa: BLE001 — 岛处理失败按 water（不阻断整文件）
        return None
    if not first.get("success"):
        return None
    out = first.get("output") or ""
    if not out.strip():
        return None

    try:
        second = _run(out, rules_dir, ext_dirs)
    except Exception:  # noqa: BLE001 — 重解析失败按 water
        return None
    if not second.get("success"):
        return None
    out2 = second.get("output") or ""
    if out2 != out:  # 双跑幂等（逐字；不是"能再次解析"就算过）
        return None
    return out
