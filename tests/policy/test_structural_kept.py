"""判保持登记表完整性门禁 —— `tools/structural_kept.json` 不许出现"没人管的项"。

动机：`policy/structural_budget.md` 的口径是 **S 度量"未经处置的欠账"**，
逐项下结论后该项从 S 里出去（R6）。这条口径成立的前提是**登记表本身可信**：
一旦有人塞进一条空理由、或写了一个**指向已不存在路径**的键，S 会照旧显示 0，
而"保持"就退化成"没看"——正是 `structural_budget.md` 明令禁止的形态
（"没有理由的项不许进这里"）。此前无任何测试守这份表。

两件断言：
1. **理由非空且有实质长度**：每条值必须是够长的说明（"保持"是结论，不是占位符）。
2. **键可解析到真实定义**：把键里的符号全名解析成文件 + 定义名，断言文件存在、
   定义名在文件里是 `def` / `class`。⚠ 这一条是**结构性改动的前哨**——精化基座
   重构（把 `analyzer/` 的部件搬进语言包插件）会移动文件，键里的路径随之失效；
   有这道断言就当场变红（暴露"登记表静默腐烂"），而不是等到下次审计才发现。

为何不进 smoke 快速层：审计线**刻意不进日常门禁**（需外部二进制、分钟级，
见 `policy/bifrost_audit.md`），而这份表只在审计工作时变动——放全量门禁即可。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KEPT_PATH = ROOT / "tools" / "structural_kept.json"

FAMILIES = {"CC", "COG", "FUNC", "CLASS", "CLONE"}
MIN_REASON_LEN = 30          # 短于此不构成"理由"（实测最长理由 200+ 字）


def _load() -> dict[str, str]:
    data = json.loads(KEPT_PATH.read_text(encoding="utf-8"))
    return data["items"]


def _defined_names(path: Path) -> set[str]:
    """文件里全部 `def` / `class` 名（含嵌套定义）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _split_fqn(fqn: str) -> tuple[Path, str]:
    """符号全名 → (文件, 定义名)。按最长可解析前缀定位文件。

    支持 `pkg.mod.func` 与 `pkg/mod/__init__.py` 两种落点；解析不出文件则抛断言。
    """
    parts = fqn.split(".")
    for k in range(len(parts) - 1, 0, -1):
        rel = "/".join(parts[:k])
        for candidate in (ROOT / f"{rel}.py", ROOT / rel / "__init__.py"):
            if candidate.is_file():
                return candidate, parts[k:][-1] if k < len(parts) else ""
    pytest.fail(f"键里的符号解析不到文件：{fqn!r}（路径已失效？见模块 docstring）")


def _targets(key: str) -> list[str]:
    """一个键涉及的符号全名列表（CLONE 两侧、CLASS 的 `path:Name` 单独处理）。"""
    body = key.split("|", 1)[1]
    if key.startswith("CLASS|"):
        return []
    if key.startswith("CLONE|"):
        return [side.strip() for side in body.split("<->")]
    return [body.strip()]


def test_ledger_is_not_empty() -> None:
    """表非空——被清空说明口径被绕过（S=0 就不再是"已下结论"）。"""
    assert _load(), "structural_kept.json 的 items 为空"


def test_every_entry_has_a_real_reason() -> None:
    """每条必须有实质理由（R6：'保持'是结论，不是'没看'）。"""
    bad = {
        key: value
        for key, value in _load().items()
        if not isinstance(value, str) or len(value.strip()) < MIN_REASON_LEN
    }
    assert not bad, f"以下条目缺实质理由：{sorted(bad)}"


def test_every_key_has_a_known_family() -> None:
    """键形 `FAMILY|...`，族名在 CC/COG/FUNC/CLASS/CLONE 内。"""
    unknown = [k for k in _load() if k.split("|", 1)[0] not in FAMILIES]
    assert not unknown, f"未知族名（键形 `FAMILY|...`）：{unknown}"


def test_class_keys_point_to_existing_definitions() -> None:
    """`CLASS|<path>:<Name>` → path 存在且 Name 是其中的类定义。"""
    for key in _load():
        if not key.startswith("CLASS|"):
            continue
        rel, _, name = key.split("|", 1)[1].partition(":")
        target = ROOT / rel
        assert target.is_file(), f"{key}：文件不存在（{rel}）——路径已失效"
        assert name in _defined_names(target), f"{key}：{rel} 里没有定义 {name}"


def test_symbol_keys_resolve_to_existing_definitions() -> None:
    """CC/COG/FUNC/CLONE 键 → 文件存在且定义名在文件中（搬家后当场变红）。"""
    for key, value in _load().items():
        for fqn in _targets(key):
            path, name = _split_fqn(fqn)
            assert name in _defined_names(path), (
                f"{key}：{path.relative_to(ROOT).as_posix()} 里没有定义 {name}"
                f"（理由记的是：{value[:40]}…）"
            )
