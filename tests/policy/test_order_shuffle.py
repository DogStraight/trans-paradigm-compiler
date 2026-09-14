"""顺序随机化 hook（`TPC_SHUFFLE_SEED`）——顺序巡检档的自保。

L3 把"幽灵 flake"从偶发变成必现靠的是文件级乱序 + 固定种子（复现性）。
本文件锁 hook 的判据：同种子同序（可复现）、**不拆散**同文件用例（模块级
fixture 的作用域语义）、未设环境变量时不动原序。
"""
from types import SimpleNamespace

import pytest

from tests import conftest

pytestmark = pytest.mark.smoke

_NODEIDS = [
    "tests/a/test_one.py::test_1",
    "tests/a/test_one.py::test_2",
    "tests/b/test_two.py::test_1",
    "tests/c/test_three.py::test_1",
    "tests/c/test_three.py::test_2",
    "tests/d/test_four.py::test_1",
]


def _shuffled(nodeids: list[str], seed: str | None, monkeypatch) -> list[str]:
    if seed is None:
        monkeypatch.delenv("TPC_SHUFFLE_SEED", raising=False)
    else:
        monkeypatch.setenv("TPC_SHUFFLE_SEED", seed)
    items = [SimpleNamespace(nodeid=n) for n in nodeids]
    conftest.pytest_collection_modifyitems(SimpleNamespace(), items)  # type: ignore[arg-type]
    return [i.nodeid for i in items]


@pytest.mark.parametrize("seed", ["1", "7", "42"])
def test_same_seed_same_order(seed, monkeypatch) -> None:
    """同种子两次结果相同——失败可复现的前提。"""
    assert _shuffled(_NODEIDS, seed, monkeypatch) == _shuffled(_NODEIDS, seed, monkeypatch)


def test_files_stay_contiguous(monkeypatch) -> None:
    """同文件用例不被拆散（模块级 fixture 的作用域语义）。"""
    for seed in ("1", "7", "42"):
        got = _shuffled(_NODEIDS, seed, monkeypatch)
        assert sorted(got) == sorted(_NODEIDS), "乱序不应增删用例"
        for path in {n.split("::", 1)[0] for n in _NODEIDS}:
            idx = [i for i, n in enumerate(got) if n.startswith(path + "::")]
            assert idx == list(range(idx[0], idx[0] + len(idx))), f"{path} 被拆散：{got}"


def test_no_env_keeps_collection_order(monkeypatch) -> None:
    assert _shuffled(_NODEIDS, None, monkeypatch) == _NODEIDS


def test_seeds_can_differ(monkeypatch) -> None:
    """不同种子至少能给出不同文件序（hook 真的在洗牌，不是恒等映射）。"""
    orders = {tuple(_shuffled(_NODEIDS, s, monkeypatch)) for s in ("1", "2", "3", "4")}
    assert len(orders) > 1, f"四种种子给出同一顺序，hook 未生效：{orders}"
