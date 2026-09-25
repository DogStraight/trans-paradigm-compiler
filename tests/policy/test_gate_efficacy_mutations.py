"""变异门禁的**自校验**（0.1.3 WS2 步 2b）：每条变异必须仍然"活着"。

**问题**：`tools/check_gate_efficacy.py` 的每条变异用 `old` 字符串去替换目标文件里的
片段。目标文件一改（键名变了、行被重排、码被删），`old` 就**匹配不上**——此时工具
要么静默跳过、要么报一个与"门禁失灵"无关的错。**变异的失效本身就是门禁的失效**，
而它不会自己喊出来。

**做法**（静态、零执行代价，不跑被测门禁）：

1. `file` / `test` 指向的文件必须存在；
2. `old` 必须**仍出现在 `file` 里**（可应用——否则该变异已失效）；
3. `old` / `new` 载荷里形如诊断码的字面量必须是**已定义码**（码改名/删除后不得留残余）。

⚠ 不在此断言"变异后确实变红"——那要跑被测门禁（分钟级），属按需人工跑
（`policy/release-checklist.md` 与 `tools/README.md` 的工具定位）。

Doc: docs/gaps/gap-feature-scatter.md（步 2 收敛与剩余项）
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests._rule_codes import all_codes, code_like  # noqa: E402

_TOOL = os.path.join(_ROOT, "tools", "check_gate_efficacy.py")


def _mutations() -> list[dict]:
    spec = importlib.util.spec_from_file_location("check_gate_efficacy", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod._MUTATIONS)


def _ids() -> list[str]:
    return [m["why"][:38] for m in _mutations()]


@pytest.mark.parametrize("mutation", _mutations(), ids=_ids())
def test_mutation_targets_exist(mutation):
    for key in ("file", "test"):
        path = os.path.join(_ROOT, mutation[key])
        assert os.path.isfile(path), f"变异 {key} 不存在: {mutation[key]}"


@pytest.mark.parametrize("mutation", _mutations(), ids=_ids())
def test_mutation_payload_still_applies(mutation):
    """`old` 必须仍出现在目标文件里——否则该变异已静默失效（门禁是假的）。"""
    path = os.path.join(_ROOT, mutation["file"])
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert mutation["old"] in text, (
        f"变异已失效：old 片段在 {mutation['file']} 里找不到。"
        f"目标文件改了就得同步更新该变异（否则这条门禁形同不存在）。\n"
        f"old = {mutation['old']!r}"
    )


@pytest.mark.parametrize("mutation", _mutations(), ids=_ids())
def test_mutation_payload_codes_are_defined(mutation):
    """载荷里形如诊断码的字面量必须是已定义码（码改名/删除后不留残余）。"""
    defined = all_codes()
    for key in ("old", "new"):
        for token in re.findall(r"\b[A-Z]{1,4}\d{2,4}\b", mutation[key]):
            if code_like(token):
                assert token in defined, (
                    f"变异载荷里的诊断码 {token!r} 未定义（码已改名或删除？）"
                )
