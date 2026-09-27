"""tests/policy/test_edge_corpus_provenance.py — edge 语料抬头纪律（沉淀产物的门禁）。

背景：fuzz 回馈链路的最后一步是"最小复现 + 溯源抬头 → 落进 edge 语料"
（`tests/fuzz/shrink.py --sediment`）。自动落盘能跑，但**抬头是给人看的**——
它必须说清"这条语料的判定是什么、从哪来"。缺了它，语料退化成一堆无主文件；
判定与所在目录不一致时，门禁会在错误的方向上锁行为。

判据（只对**沉淀产物**生效：抬头含 `fuzz 回归` 的那些——手写语料的抬头格式
没有统一约定，不在此约束）：

1. 抬头必须点名判定 `edge clean` / `edge reject`，且与所在目录**一致**；
2. 抬头**日期 ≥ 2026-09-26** 的必须写明 fuzz 类别（`fuzz 类别 <kind>`）——
   它是 `run_edge.py` 复检不变量时的登记项。此前的四条（2026-08-22 手工沉淀）
   豁免：它们记录的是"静默丢内容/崩溃"这类**当时还没有类别名**的失败模式，
   硬凑一个现有类别反而是造假；按日期分界比"给历史补一个不存在的类别"诚实。
3. 类别若写了，必须是 `oracle` 认识的类别（改类别名/写错要在这里红）；
4. **不得留 `成因待补`**：自动沉淀可以先把判定固定下来，但成因是知识，
   不能以"待补"状态合进主干（否则下一个人只看到一条无解释的语料）。

Doc: tests/fuzz/README.md（回馈链路）；tests/fuzz/shrink.py（抬头生成）
"""

from __future__ import annotations

import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "tests", "fuzz"))

import oracle  # noqa: E402

_CORPORA = [
    os.path.join(_ROOT, "tests", "edge", "edge_corpus"),
]

_JUDGE_RE = re.compile(r"edge (clean|reject)")
_KIND_RE = re.compile(r"fuzz 类别 ([a-z-]+)")
_DATE_RE = re.compile(r"fuzz 回归 (\d{4}-\d{2}-\d{2})")
# 类别抬头从此日起成为沉淀的必备项（此前的四条手工沉淀豁免，理由见模块 docstring）
_KIND_REQUIRED_FROM = "2026-09-26"


def _corpus_files() -> list[tuple[str, str]]:
    """[(abs 路径, 期望判定)]——只收沉淀产物（抬头含 `fuzz 回归`）。"""
    out: list[tuple[str, str]] = []
    for root in _CORPORA:
        for judge in ("clean", "reject"):
            d = os.path.join(root, judge)
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                path = os.path.join(d, name)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    head = f.read(400)
                if "fuzz 回归" in head:
                    out.append((path, judge))
    return out


_FILES = _corpus_files()


def test_every_corpus_file_starts_with_a_comment_header():
    """全部边缘语料（含手写）必须带抬头——无主语料没法追溯来历。"""
    for root in _CORPORA:
        for judge in ("clean", "reject"):
            d = os.path.join(root, judge)
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                path = os.path.join(d, name)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    first = f.readline()
                assert first.startswith("//"), f"{name} 缺抬头注释：{first!r}"


@pytest.mark.parametrize("path,judge", _FILES, ids=[os.path.basename(p) for p, _ in _FILES])
def test_sedimented_header_declares_matching_judgement(path, judge):
    with open(path, encoding="utf-8") as f:
        head = f.read(400)
    m = _JUDGE_RE.search(head)
    assert m, f"沉淀语料抬头没写判定（edge clean/reject）：{path}"
    assert m.group(1) == judge, (
        f"抬头判定 {m.group(1)} 与所在目录 {judge} 不一致：{path}"
    )
    d = _DATE_RE.search(head)
    assert d, f"沉淀语料抬头没写日期（（fuzz 回归 YYYY-MM-DD））：{path}"
    kind = _KIND_RE.search(head)
    if d.group(1) >= _KIND_REQUIRED_FROM:
        assert kind, (
            f"{d.group(1)} 起的沉淀语料必须写 `fuzz 类别 <kind>`（run_edge 靠它复检"
            f"不变量）：{path}"
        )
    if kind:
        assert kind.group(1) in oracle.ALL_KINDS, (
            f"抬头登记的类别 {kind.group(1)!r} 不是 oracle 认识的类别"
            f"（改类别名后须同步）：{path}"
        )
    assert "成因待补" not in head, (
        f"沉淀语料抬头仍是「成因待补」——自动沉淀固定了判定，成因须人补：{path}"
    )
