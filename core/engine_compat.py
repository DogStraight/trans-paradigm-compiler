"""engine_compat.py — 语言包声明的引擎 API 兼容校验（fail-fast）。

语言包 `grammar/<lang>/tpc.toml` 可声明：

    [engine]
    api = "0.1"      # 该包构建所依据的引擎 API 线（major.minor）

含义：语言包依赖引擎语义（FOLLOW 推导 / inject / 节点绑定 / 组件协议），
0.x 期 minor 变动即可能破坏旧包。声明后，引擎 major.minor 不匹配即**拒绝加载**
（ConfigError）——替掉"升级引擎后包静默坏掉"的隐式契约。

未声明 = 不校验（纯增量：便于 ad-hoc 包与测试夹具；内置三包均声明）。

校验点两处（各自是不同的入口，都不可省）：
- `core/config_registry.py::_load_meta_declarations`（`load_all` / `resolve` 路径）
- `core/define.py::_load_tpc_meta`（import 期默认包路径）

Doc: core/config_lifecycle.md（配置生命周期）
"""

from __future__ import annotations

from core.errors import ConfigError

_SECTION = "engine"
_KEY = "api"


def api_line(version: str) -> str:
    """取版本串的 API 线（major.minor）。"""
    parts = version.split(".")
    if len(parts) < 2 or not all(parts[:2]):
        raise ConfigError(
            f"[engine] 版本串需 major.minor 形态（如 0.1.1），实得 {version!r}"
        )
    return ".".join(parts[:2])


def engine_api_line() -> str:
    """当前引擎的 API 线（延迟导入 core，避开 core/__init__ → define → 本模块 的环）。"""
    from core import __version__

    return api_line(__version__)


def check_engine_compat(meta: dict, pack_label: str) -> None:
    """校验语言包 `[engine]` 声明与当前引擎是否兼容（不兼容即抛 ConfigError）。

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
            f"（形如 `{_KEY} = \"0.1\"`），实得 {section!r}"
        )
    declared = section.get(_KEY)
    if declared is None:
        raise ConfigError(
            f"[engine] {pack_label}：tpc.toml [{_SECTION}] 声明了段落但缺 "
            f"{_KEY} 键（应为 \"<major>.<minor>\"，如 \"0.1\"）"
        )
    if not isinstance(declared, str) or not declared.strip():
        raise ConfigError(
            f"[engine] {pack_label}：[{_SECTION}].{_KEY} 须为非空字符串，"
            f"实得 {declared!r}"
        )
    want = declared.strip()
    have = engine_api_line()
    if want != have:
        raise ConfigError(
            f"[engine] {pack_label}：语言包声明的引擎 API 线为 {want}，"
            f"当前引擎为 {have}——包与引擎不兼容（语言包依赖引擎语义："
            f"FOLLOW 推导 / inject / 节点绑定），请升级语言包或改用匹配的引擎"
        )
