"""tests/engine/preprocessor/test_expand_timeline.py — 宏展开定义时间线（T1）。

判据（`docs/gaps/gap-preprocessor-macro-timeline.md`）：
  1. 本文件定义前文本不按宏展开；`#undef` 后不展开；重定义后按新体展开；
  2. include 内容按**头内**定义顺序展开（原型在头内 #define 之前 ⇒ 不展开）；
  3. include 后宿主可见头内最终宏（C §6.10.2/§6.10.3）。
入口 = `scan_directives(out_macro_events=...)` + `expand_tokens(events=...,
clean_to_raw=...)`（生产管线同路；事件表 = 定义/取消时刻的权威顺序）。
"""

from __future__ import annotations

from pathlib import Path

from preprocessor import scan_directives
from preprocessor._expand import expand_tokens

PACK = "grammar/c"


def _expand(src: str, *, path: str | None = None, search: list[str] | None = None) -> str:
    events: list[dict] = []
    macro_table, func_macros, _, _, _, clean, clean_to_raw = scan_directives(
        src,
        PACK,
        source_path=path,
        search_dirs=search or [],
        out_macro_events=events,
    )
    return expand_tokens(
        clean,
        macro_table,
        rules_dir=PACK,
        func_macros=func_macros,
        events=events,
        clean_to_raw=clean_to_raw,
    )[0]


def test_use_before_define_not_expanded() -> None:
    """本文件定义前：原型/调用保持原文（旧"最终表"近似会误展开）。"""
    out = _expand("int F(int);\n#define F(a, b) ((a) + (b))\nint g(void){ return F(1, 2); }\n")
    assert "int F(int);" in out, out
    assert "((1) + (2))" in out, out


def test_undef_stops_expansion() -> None:
    out = _expand("#define X 1\nint a = X;\n#undef X\nint b = X;\n")
    assert "int a = 1;" in out, out
    assert "int b = X;" in out, out


def test_redefinition_uses_latest_body() -> None:
    out = _expand("#define X 1\nint a = X;\n#define X 2\nint b = X;\n")
    assert "int a = 1;" in out, out
    assert "int b = 2;" in out, out


def test_include_internal_order_prototype_before_define(tmp_path: Path) -> None:
    """头内：原型在 #define 之前 ⇒ 原型不展开（zlib gzgetc 型真实语料形态）。"""
    (tmp_path / "h.h").write_text(
        "extern int gzgetc(int);\n#define gzgetc(g) ((g)->have)\n", encoding="utf-8"
    )
    out = _expand(
        '#include "h.h"\nint use(void){ return gzgetc(0); }\n',
        path=str(tmp_path / "a.c"),
        search=[str(tmp_path)],
    )
    assert "extern int gzgetc(int);" in out, out
    assert "((0)->have)" in out, out


def test_include_macro_visible_after_include(tmp_path: Path) -> None:
    (tmp_path / "h.h").write_text("#define LIMIT 7\n", encoding="utf-8")
    out = _expand(
        '#include "h.h"\nint n = LIMIT;\n',
        path=str(tmp_path / "b.c"),
        search=[str(tmp_path)],
    )
    assert "int n = 7;" in out, out


def test_include_content_not_double_expanded(tmp_path: Path) -> None:
    """头内已按包含点可见宏集展开；宿主不得用最终表二次展开头内文本。"""
    (tmp_path / "h.h").write_text(
        "int a = 1;\n#define LATE 9\nint b = LATE;\n", encoding="utf-8"
    )
    out = _expand(
        '#include "h.h"\nint c = LATE;\n',
        path=str(tmp_path / "c.c"),
        search=[str(tmp_path)],
    )
    # 头内 `LATE` 定义前：若被宿主二次展开会出现 `int a = 1;` 之外的 9 提前出现
    assert "int b = 9;" in out, out
    assert "int c = 9;" in out, out
    assert out.count("9") == 2, out


def test_include_guard_visible_across_sibling_includes(tmp_path: Path) -> None:
    """include guard 跨多次 include 可见（子扫描继承包含点宏环境）。

    同一守卫头被宿主 include 两次 ⇒ 第二次应整体跳过（`#ifndef` 为假），
    内容只出现一次；不继承时第二次会重复铺入（真实语料 zlib 二次定义命中）。
    """
    (tmp_path / "h.h").write_text(
        "#ifndef H_H\n#define H_H\nint guarded;\n#endif\n", encoding="utf-8"
    )
    out = _expand(
        '#include "h.h"\n#include "h.h"\nint use = guarded;\n',
        path=str(tmp_path / "d.c"),
        search=[str(tmp_path)],
    )
    assert out.count("int guarded;") == 1, out
