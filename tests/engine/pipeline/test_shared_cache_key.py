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


def _run(ext_dirs):
    return run_pipeline_on_source(
        source=_SRC, quiet=True, no_lint=True, ext_dirs=ext_dirs
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
