"""能力协商覆盖门禁（0.1.3 WS2 步 3）——语言包不许漏声明它用到的能力。

**问题**：能力协商的收益取决于"包声明的 `uses` 真的是它依赖的面"。若包用到了
`[structure]` 段却忘了声明 `structure.protocol`，引擎将来改该能力时**不会**拦下这个包
——协商就退化回"靠人记着同步"（正是本议题要消灭的东西）。

**做法**（单一来源）：`core/engine_capabilities.py::required_capabilities()` 从语言包
**自己的清单**（tpc.toml 段 + `[capabilities]` 键 + `rules/*.toml` 存在性）机械推导所需
能力；本门禁断言每个内置包 **推导集 ⊆ 声明集**，并对每个声明项跑一次真实协商。

⚠ 分工（避免同一断言两处写=新散点）：**协商语义**（合法/非法/点名报错/未声明不误伤）
在 `tests/engine/core/test_engine_compat.py`；本门禁只管**仓库不变式**（覆盖与衍生）。

Doc: core/config_lifecycle.md（包↔引擎契约节）
"""
from __future__ import annotations

import os
import sys
import tomllib

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core import engine_capabilities as caps  # noqa: E402
from core.engine_compat import check_engine_compat  # noqa: E402


def _packs() -> list[str]:
    """内置语言包（grammar/ 下有 tpc.toml 的目录）。"""
    root = os.path.join(_ROOT, "grammar")
    return sorted(
        name
        for name in os.listdir(root)
        if os.path.isfile(os.path.join(root, name, "tpc.toml"))
    )


def test_capability_table_is_wellformed():
    """能力表非空 + 版本号是纯数字（`uses` 形态 `name.vN` 依赖它）。"""
    assert caps.CAPABILITIES, "能力表为空——协商无从谈起"
    for name, ver in caps.CAPABILITIES.items():
        assert name and "." in name, f"能力名 {name!r} 应带分组前缀（如 lexer.token_ext）"
        assert str(ver).isdigit(), f"能力 {name} 版本 {ver!r} 应为纯数字"


@pytest.mark.parametrize("pack", _packs())
def test_pack_declares_every_capability_it_uses(pack):
    """推导集 ⊆ 声明集：清单段用到的能力必须声明（漏声明即红）。"""
    pack_dir = os.path.join(_ROOT, "grammar", pack)
    with open(os.path.join(pack_dir, "tpc.toml"), "rb") as f:
        meta = tomllib.load(f)
    uses = set(meta.get("engine", {}).get("uses", []))
    derived = {
        f"{c}.v{caps.CAPABILITIES[c]}" for c in caps.required_capabilities(pack_dir)
    }
    assert derived <= uses, (
        f"grammar/{pack} 漏声明能力（清单段用到了却没说，"
        f"引擎改该能力时不会拦下这个包）：{sorted(derived - uses)}"
    )
    check_engine_compat(meta, f"grammar/{pack}")


@pytest.mark.parametrize("pack", _packs())
def test_pack_uses_has_no_stale_capability(pack):
    """声明集 ⊆ 能力表：`uses` 里不许留引擎已不认识的能力（改名/删除的残留）。"""
    with open(os.path.join(_ROOT, "grammar", pack, "tpc.toml"), "rb") as f:
        meta = tomllib.load(f)
    for token in meta.get("engine", {}).get("uses", []):
        name, _, ver = token.rpartition(".v")
        assert name in caps.CAPABILITIES, (
            f"grammar/{pack} 声明了引擎不认识的能力 {name!r}（能力已改名或删除？）"
        )
        assert ver == caps.CAPABILITIES[name], (
            f"grammar/{pack} 的能力 {name!r} 版本滞后：声明 v{ver}，引擎 v"
            f"{caps.CAPABILITIES[name]}"
        )
