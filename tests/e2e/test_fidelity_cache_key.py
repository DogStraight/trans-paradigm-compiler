"""e2e 脚本保真度缓存按内容键控（2026-09-14 测试隔离 L2）。

`.fidelity_cache.json` 是 run_all_tests.py 的本地基线（gitignored）：只按
`name@mode` 记保真度时，样本源改过之后旧值会被拿来与新内容比 → 幻影 drop
（或反向漏检真实下降）。本文件锁 `_cached_prev` 的键控判据：摘要不符即不算
基线，旧格式条目一并作废（本地状态，不保留兼容）。
"""
import pytest

from tests.e2e.run_all_tests import _cached_prev, _source_digest

pytestmark = pytest.mark.smoke


def test_matching_digest_returns_prev() -> None:
    digest = _source_digest("module m; endmodule")
    entry = {"sha": digest, "fidelity": 0.95}
    assert _cached_prev(entry, digest) == pytest.approx(0.95)


def test_digest_mismatch_is_no_baseline() -> None:
    """样本源改了 → 旧保真度不能当基线（否则报幻影 drop）。"""
    entry = {"sha": _source_digest("old source"), "fidelity": 0.95}
    assert _cached_prev(entry, _source_digest("new source")) is None


def test_legacy_or_broken_entries_ignored() -> None:
    digest = _source_digest("module m; endmodule")
    for entry in (0.95, None, {}, {"sha": digest}, {"sha": digest, "fidelity": "x"}):
        assert _cached_prev(entry, digest) is None, entry
