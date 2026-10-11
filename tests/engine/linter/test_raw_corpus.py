"""raw 语料逐条枚举（`corpus_raw/`）：合格位点数 + 可见变化面（M2+raw 批次）。

为什么新造：既有语料 `tests/e2e/samples/**` 里 `eligible` 位点数为 **0** ⇒ 用它对拍
`--expect-changed 0` 是**空证据**。本目录每条 `.c` 都带期望值，本文件逐条断言。

覆盖上下文（task-29 冻结面 = 顶层 + `CompoundStmt` 直接子语句）：
  · `fn_body.c`      CompoundStmt 直接子语句（函数体）：合格 1、被摘 1；
  · `top_level.c`    顶层：合格 1、被摘 2；
  · `decl_excluded.c` 声明句互斥（`int t = (u)v;`）：合格 **0**（不摘不 raw），真错仍报；
  · `single_body.c`  函数体内 if 单语句体：合格 1，但诊断报在**容器起点**、不在 site
                     region ⇒ **不摘**（覆盖面不扩，不得为扩覆盖放宽位置匹配）；
  · `counter_expr.c` 反例：合格 0、真错仍报 2 条 blocking。
"""

from pathlib import Path

import pytest

from core.define import DEFAULT_RULES_DIR

C_PACK, C_PLUGINS = "grammar/c", "grammar/c/plugins"
CORPUS_DIR = Path(__file__).parent / "corpus_raw"

#: 文件 → (期望 blocking **条数**, 期望合格位点数, 期望被摘诊断数)
# ⚠ 只锁条数、不锁具体码：analyzer 接入后反例可能换码（lint 的 phase-* → analyzer 的
# E002），判据只要求"仍有 blocking + 管线失败"（Lead 裁定）。
EXPECT: dict[str, tuple[int, int, int]] = {
    "fn_body.c": (0, 1, 1),
    "top_level.c": (0, 1, 2),
    "decl_excluded.c": (1, 0, 0),
    "single_body.c": (1, 1, 0),
    "counter_expr.c": (2, 0, 0),
}


@pytest.fixture
def c_scanner(config_loaded):
    del config_loaded
    from core.config_registry import ConfigRegistry
    from linter.scanner import LinterScanner

    ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
    try:
        yield LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_corpus_eligibility_and_visible_surface(c_scanner, name):
    expected_blocking, expected_eligible, expected_suppressed = EXPECT[name]
    src = (CORPUS_DIR / name).read_text(encoding="utf-8")
    diags = c_scanner.scan(src)
    warns = c_scanner.internal_warnings()

    blocking = [d for d in diags if d.blocking]
    assert len(blocking) == expected_blocking, f"{name}: blocking 条数变了（真错被吞/多了误报）"
    eligible = [w for w in warns if w["eligible"]]
    assert len(eligible) == expected_eligible, f"{name}: 合格位点数变了"
    suppressed = sum(int(w.get("suppressed", 0)) for w in warns)
    assert suppressed == expected_suppressed, f"{name}: 被摘诊断数变了"


def test_corpus_covers_both_contexts(c_scanner):
    """覆盖面证据：函数体（CompoundStmt 直接子语句）与顶层都要有合格位点。"""
    total = 0
    for name in ("fn_body.c", "top_level.c"):
        src = (CORPUS_DIR / name).read_text(encoding="utf-8")
        c_scanner.scan(src)
        hits = [w for w in c_scanner.internal_warnings() if w["eligible"]]
        assert len(hits) == 1, name
        assert hits[0]["symbol_names"] == ["myint"]
        total += len(hits)
    assert total == 2


def test_corpus_declaration_excluded_by_mutex(c_scanner):
    """raw 互斥：声明句的合格位点必须为 0（否则 raw 会让声明不进符号表）。"""
    src = (CORPUS_DIR / "decl_excluded.c").read_text(encoding="utf-8")
    c_scanner.scan(src)
    warns = c_scanner.internal_warnings()
    assert warns, "应有未收敛记录"
    assert all(w["eligible"] is False for w in warns)
    assert all(w["raw_exclude_hits"] for w in warns), "互斥证据应记录命中的声明类规则"
