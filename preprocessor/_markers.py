"""引擎内部占位 marker（`tpc:<kind>:<seq>`）的书写与识别。

marker 必须**以注释形态**穿过管线（parser 当 trivia 跳过、渲染端保留注释，
渲染后才由还原侧按 marker 定位回插原文），所以书写标点 = 语言的注释标点，
全部来自语言包声明（`lexer/comment_syntax.py`）——引擎不认识 `//` / `/* */`。
两种形态：

  - **整行**（`line_marker`）：行注释占位，独占一行。条件块占位、整行宏锚、
    指令行占位用——整行插入/替换，还原时整行换回原文段。
  - **行内**（`inline_marker`）：块注释占位，可出现在行中。空体宏 / 赋值后缀宏
    锚用——token 位置替换会造出相邻原子（`id` + 位宽字面量）不可解析，块注释
    是 trivia，parser 跳过。

识别侧只用 `tpc:` 核心（`marker_core_re`：从任意文本取 `<tpc:…>` 编号）或
**已写好的形态**（`line_form_re` 扫整行占位、还原侧按 `line_marker` 拼文本）——
不在识别处重新拼注释标点。

语言包未声明所需形态（如只有行注释、无块注释的 c4）而该形态又被需要 →
fail-fast（配置缺失不静默降级）。
Doc: preprocessor/README.md（tpc marker 通道）
Doc: renderer/renderer_architecture.md（注释单机制：tpc marker）
"""

import re

from lexer.comment_syntax import CommentSyntax


def line_marker(syntax: CommentSyntax, marker: str) -> str:
    """整行占位文本（行注释形态，如 `// <tpc:cond:0>`）。"""
    start = syntax.line_start
    if start is None:
        raise ValueError(
            "[preprocessor] 语言包未声明行注释（[comment] pairs 里 kind=\"line\"），"
            f"无法写出整行占位 marker: {marker!r}"
        )
    return f"{start} <{marker}>"


def inline_marker(syntax: CommentSyntax, marker: str) -> str:
    """行内占位文本（块注释形态，如 `/*<tpc:macro:0>*/`）。"""
    open_ = syntax.block_open
    close = syntax.block_close
    if open_ is None or close is None:
        raise ValueError(
            "[preprocessor] 语言包未声明成对注释定界符（[comment] pairs 里 "
            f"kind=\"block\"），无法写出行内占位 marker: {marker!r}"
        )
    return f"{open_}<{marker}>{close}"


def line_form_re(syntax: CommentSyntax) -> re.Pattern:
    """匹配**独占整行的占位**（可带前导缩进/尾部空白），捕获 marker 编号。

    两处消费：还原侧按 marker 编号比对（整行换回原文段）、扫描侧收集"已随
    渲染/清洁流出现的整行占位"（插值锚点、源行号映射）。
    """
    start = syntax.line_start
    if start is None:
        # 未声明行注释 → 永不匹配的形态（扫描侧容忍，书写侧才 fail-fast）
        return re.compile(r"(?!x)x")
    return re.compile(
        rf"^[ \t]*{re.escape(start)}[ \t]*<({_marker_core_pattern()})>[ \t]*$",
        re.MULTILINE,
    )


def _marker_core_pattern() -> str:
    """marker 编号的捕获模式（`tpc:<kind>:<seq>`）。"""
    return r"tpc:[^>]+"


def marker_core_re() -> re.Pattern:
    """从任意文本取 marker 编号（`<tpc:…>` 内的部分）。"""
    return re.compile(rf"<({_marker_core_pattern()})>")
