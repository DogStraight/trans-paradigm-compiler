"""管线共享组件缓存键 = (rules_dir, ext_dirs)（2026-09-14 测试隔离 L2）。

只键 rules_dir 时，同一语言的两次调用若 ext_dirs 不同会静默复用组件——
Lexer/LinterScanner/规则注入都吃 ext_dirs，复用即拿到上一组扩展目录的
组件与规则（错得很安静）。本文件锁：不同 ext_dirs 各占一条缓存，且第二次
调用不返回第一次的组件对象。
"""
import pytest

from pipeline import _PIPELINE_SHARED, run_pipeline_on_source

pytestmark = pytest.mark.smoke

_SRC = "module m;\n  wire a;\n  assign a = 1'b0;\nendmodule\n"
_EXT = ["grammar/verilog/plugins"]  # 本仓库 DEFAULT_EXT_DIRS 为空列表，用真实扩展目录


def _run(ext_dirs, check_idempotent=None):
    return run_pipeline_on_source(
        source=_SRC,
        quiet=True,
        no_lint=True,
        ext_dirs=ext_dirs,
        check_idempotent=check_idempotent,
    )


def test_ext_dirs_part_of_cache_key() -> None:
    """同 rules_dir、不同 ext_dirs → 两条缓存条目，不复用组件。"""
    r1 = _run(_EXT)
    assert r1["success"], r1.get("error")
    keys_after_first = set(_PIPELINE_SHARED)

    r2 = _run([])
    assert r2["success"], r2.get("error")
    keys_after_second = set(_PIPELINE_SHARED)

    assert len(keys_after_second) == len(keys_after_first) + 1, (
        f"不同 ext_dirs 未各占一条缓存：{keys_after_second}"
    )
    first_rules = _PIPELINE_SHARED[next(iter(keys_after_first))]["rules"]
    second_rules = _PIPELINE_SHARED[(next(iter(keys_after_second - keys_after_first)))]["rules"]
    assert first_rules is not second_rules, "第二次调用复用了第一次的规则集"


def test_same_inputs_reuse_cache() -> None:
    """同 rules_dir + 同 ext_dirs → 复用（缓存存在的意义）。"""
    _run(_EXT)
    keys_first = set(_PIPELINE_SHARED)
    _run(_EXT)
    assert set(_PIPELINE_SHARED) == keys_first, "同参调用不应新建缓存条目"


# ── parser 进共享缓存（2026-10-29 块 11 吞吐）────────────────────────────────
# Parser 的预编译表（FIRST/FOLLOW/atom/锚点）与语言包绑定、构建 ~50ms；fuzz 每
# 迭代新建一次时占 17% 运行时间。`Parser.parse()` 每次重置全部解析期状态，故
# 最外层管线复用同一实例；**幂等复跑的嵌套管线新建**（否则覆盖外层 result 里的
# parser 注释锚点）。


def test_parser_shared_across_runs() -> None:
    """同参两次调用复用同一 Parser 实例，且结果里的 parser 就是共享实例。"""
    from parser.parser_core import Parser

    _run(_EXT, check_idempotent=False)  # 预热缓存
    created: list[int] = []
    orig_init = Parser.__init__

    def _counting(self, *a, **kw):
        created.append(1)
        return orig_init(self, *a, **kw)

    Parser.__init__ = _counting  # type: ignore[method-assign]
    try:
        r = _run(_EXT, check_idempotent=False)
    finally:
        Parser.__init__ = orig_init  # type: ignore[method-assign]
    assert r["success"], r.get("error")
    assert created == [], "同参调用重建了 Parser（预编译表被重复构建）"
    parser = next(iter(_PIPELINE_SHARED.values()))["parser"]
    assert r["parser"] is parser, "结果里的 parser 不是共享实例"


def test_idempotent_rerun_uses_fresh_parser() -> None:
    """内建幂等复跑的嵌套管线新建 parser（不复用外层实例）。"""
    from parser.parser_core import Parser

    _run(_EXT)  # 预热缓存
    created: list[int] = []
    orig_init = Parser.__init__

    def _counting(self, *a, **kw):
        created.append(1)
        return orig_init(self, *a, **kw)

    Parser.__init__ = _counting  # type: ignore[method-assign]
    try:
        r = run_pipeline_on_source(
            source=_SRC,
            quiet=True,
            no_lint=True,
            ext_dirs=_EXT,
            check_idempotent=True,
        )
    finally:
        Parser.__init__ = orig_init  # type: ignore[method-assign]
    assert r["success"], r.get("error")
    assert r["idempotent"] is True
    shared = next(iter(_PIPELINE_SHARED.values()))["parser"]
    assert r["parser"] is shared, "外层结果被嵌套管线替换"
    assert len(created) == 1, f"嵌套管线应新建 1 个 parser，实际 {len(created)}"

