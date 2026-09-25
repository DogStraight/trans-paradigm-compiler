"""engine_compat.py — 语言包声明的**引擎能力协商**（fail-fast）。

语言包 `grammar/<lang>/tpc.toml` 声明：

    [engine]
    uses = ["lexer.token_ext.v1", "parser.pratt.v1"]

含义：该包**依赖的引擎契约面**逐项列出（能力表与版本语义见
`core/engine_capabilities.py`）。每项须是引擎已知能力且版本匹配，否则**拒绝加载**
（ConfigError，报错点名是哪一项能力）。替掉旧契约 `[engine] api = "0.1"`——那是
**整条 API 线**：引擎 minor 一动所有包都被拦，且说不出缺什么（0.1.3 WS2 步 3）。

未声明 `[engine]` 段 = 不校验（纯增量：便于 ad-hoc 包与测试夹具；内置三包均声明）。

⚠ **不留向后兼容**：`[engine]` 段只认 `uses` 一个键——残留的 `api = "0.1"` 会被
"未知键"在加载期拦下（响亮失败，不静默忽略）。

校验点两处（各自是不同的入口，都不可省）：
- `core/config_registry.py::_load_meta_declarations`（`load_all` / `resolve` 路径）
- `core/define.py::_load_tpc_meta`（import 期默认包路径）

Doc: core/config_lifecycle.md（包↔引擎契约）
"""

from __future__ import annotations

from core.engine_capabilities import check_uses
from core.errors import ConfigError

_SECTION = "engine"
_KEY = "uses"
_ALLOWED_KEYS: frozenset[str] = frozenset({_KEY})


def check_engine_compat(meta: dict, pack_label: str) -> None:
    """校验语言包 `[engine] uses` 声明与当前引擎是否兼容（不兼容即抛 ConfigError）。

    Args:
        meta: 语言包 tpc.toml 的解析结果（未声明 [engine] 段则直接返回）。
        pack_label: 报错中显示的包标识（如 `grammar/c4`）。
    """
    section = meta.get(_SECTION)
    if section is None:
        return
    if not isinstance(section, dict):
        raise ConfigError(
            f"[engine] {pack_label}：tpc.toml [{_SECTION}] 须为表"
            f'（形如 `{_KEY} = ["lexer.token_ext.v1"]`），实得 {section!r}'
        )
    unknown = sorted(set(section) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(
            f"[engine] {pack_label}：[{_SECTION}] 含未知键: {', '.join(unknown)}"
            f"（只认 {_KEY}；旧的整条 API 线声明已删除，见 core/config_lifecycle.md）"
        )
    uses = section.get(_KEY)
    if uses is None:
        raise ConfigError(
            f"[engine] {pack_label}：tpc.toml [{_SECTION}] 声明了段落但缺 {_KEY} 键"
            f'（应为能力清单，形如 ["lexer.token_ext.v1"]；'
            f"可用能力见 core/engine_capabilities.py）"
        )
    if not isinstance(uses, (list, tuple)) or not uses:
        raise ConfigError(
            f"[engine] {pack_label}：[{_SECTION}].{_KEY} 须为非空列表，实得 {uses!r}"
        )
    check_uses(list(uses), pack_label)
