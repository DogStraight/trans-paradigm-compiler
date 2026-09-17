"""preprocessor/macro_shape.py — 宏形态声明的读取点（语言包 `[macro_recognition]`）。

宏形态用**生产式**书写（与 grammar rules 同一套规则：`,` 顺序 / `|` 选择 /
后缀 `?`/`*`/`+` / token 名），引擎只做通用解析（语言知识不进代码）：

    [macro_recognition]
    directive = "symbol.base.backtick,(macro.define|macro.undef|...)"
    call      = "symbol.base.backtick,id"

- 顺序位 0 = 前缀 token 名（`symbol.<cat>.<name>`）：符号文本取自 token 定义，
  不在引擎里硬编码语言字符；
- 顺序位 1 = 名字位：`id` = 语言包标识符（与 lexer 的 id 扫描同一实现）；写成
  token 名候选（`macro.define` …）时**命中哪个就产出哪个 token 类型**，其余
  名字 → `macro.call`（引擎协议常量，见 `core/token_protocol.py`）；
- 未声明某一段 = 该形态不识别（如 C 的宏调用就是普通标识符）。

未实现形态（后缀序 / 非符号前缀 / 多于两位）→ fail-fast（不静默降级，见
`core/config_lifecycle.md`）。

Doc: preprocessor/README.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from core.config_registry import declare_cfg
from core.errors import ConfigError
from core.token_protocol import MACRO_PREFIX

_macro_cfg: dict = declare_cfg("preprocessor.macro_config", {}, __name__, "_macro_cfg")

# 生产式 → (前缀 token 名, 名字位候选) 的内容寻址缓存（纯函数）：
# 同一生产式结果恒定，前缀文本按 token 定义另行解析（token 定义随语言包变）。
# 登记见 core/global_state.py 的 CONTENT_ADDRESSED。
_PARSE_CACHE: dict[str, tuple[str, tuple[str, ...]]] = {}

KIND_DIRECTIVE = "directive"
KIND_CALL = "call"
# 识别顺序：指令段优先（同前缀时指令优先）——lexer 与展开侧共用此顺序。
SHAPE_KINDS: tuple[str, ...] = (KIND_DIRECTIVE, KIND_CALL)
# 名字位写 `id` = 语言包标识符 token（任意名字，不参与类型判定）
NAME_TOKEN = "id"
_PREFIX_FORM = "symbol.<cat>.<name> （前缀 token 名，文本取自 token 定义）"


@dataclass(frozen=True)
class MacroShape:
    """一段宏形态：前缀文本 + 名字位候选。

    names 为空 = 名字位是任意标识符（产出 macro.call）。
    """
    kind: str
    prefix: str
    names: tuple[str, ...]

    def token_type_of(self, name: str) -> str | None:
        """名字命中的 token 类型；未命中 → None（调用方回退 `macro.call`）。

        名字位候选写成 token 名（`macro.define`）→ 扫到裸名字 `define` 时按
        协议前缀拼回候选名比对；命中即产出该 token 类型。
        """
        declared = f"{MACRO_PREFIX}{name}"
        return declared if declared in self.names else None


def load_macro_shapes(
    cfg: dict | None = None,
    token_define: dict | None = None,
    rules_dir: str | None = None,
    *,
    skip_undeclared_prefix: bool = False,
) -> dict[str, MacroShape]:
    """读取 `[macro_recognition]` → `{kind: MacroShape}`（未声明的段不出现）。

    cfg           — 宏配置（缺省：给了 rules_dir 则按该语言包解析，否则取全局声明）
    token_define  — token 定义（前缀 token 名的文本来源）
    rules_dir     — 未传 cfg / token_define 时按该语言包解析（两者同源）
    skip_undeclared_prefix — token 表由调用方自建（测试/嵌入方）时置 True：
        声明的前缀 token 不在该表里 → 跳过该形态（调用方的表说了算什么符号
        存在）；语言包自带的 token 表则 fail-fast（名字写错即配置错）。
    """
    if cfg is None:
        cfg = _resolve_macro_cfg(rules_dir) if rules_dir else _macro_cfg
    if token_define is None and rules_dir:
        from lexer.lexer_utils import get_token_define_merged

        token_define = get_token_define_merged(rules_dir)
    token_define = token_define or {}
    recognition = cfg.get("macro_recognition") or {}
    if not isinstance(recognition, dict):
        raise ConfigError(
            f"[macro_recognition] 须是表（得到 {type(recognition).__name__}）"
        )

    shapes: dict[str, MacroShape] = {}
    for kind in SHAPE_KINDS:
        production = recognition.get(kind)
        if production is None:
            continue
        if not isinstance(production, str) or not production.strip():
            raise ConfigError(
                f"[macro_recognition] {kind} 须是非空生产式字符串（得到 {production!r}）"
            )
        parsed = _PARSE_CACHE.get(production)
        if parsed is None:
            parsed = _parse_shape(kind, production)
            _PARSE_CACHE[production] = parsed
        prefix_token, names = parsed
        prefix = _prefix_text(
            prefix_token, kind, token_define, skip_undeclared_prefix
        )
        if prefix is None:
            continue
        shapes[kind] = MacroShape(kind=kind, prefix=prefix, names=names)
    return shapes


def macro_keywords(shape: MacroShape) -> tuple[str, ...]:
    """名字位候选 → 指令关键字（`macro.define` → `define`）。"""
    return tuple(name[len(MACRO_PREFIX):] for name in shape.names)


def _resolve_macro_cfg(rules_dir: str) -> dict:
    """按语言包解析宏配置（与 token 定义同源，不复用全局已加载配置）。"""
    from core.config_registry import ConfigRegistry

    resolved = ConfigRegistry.resolve(
        rules_dir, plugins_dir=os.path.join(rules_dir, "plugins")
    )
    return resolved.get("preprocessor.macro_config", {}) or {}


# ── 生产式解析（通用，不懂语言） ──


def _parse_shape(kind: str, production: str) -> tuple[str, tuple[str, ...]]:
    """生产式 → (前缀 token 名, 名字位候选 token 名)。形态非法 → ConfigError。"""
    from parser.rule_selector import analyze_production_features

    try:
        feat = analyze_production_features(production)
    except Exception as exc:  # noqa: BLE001 — 生产式语法错误即配置错（fail-fast）
        raise ConfigError(
            f"[macro_recognition] {kind} 生产式无法解析: {production!r}（{exc}）"
        ) from exc

    items = feat.get("items") if isinstance(feat, dict) else None
    if feat.get("type") != "seq" or not items or len(items) != 2:
        raise ConfigError(
            f"[macro_recognition] {kind} 形态须是两位顺序「前缀 token,名字」"
            f"（如 \"symbol.base.backtick,id\"），得到: {production!r}"
        )
    return _prefix_token(items[0], kind, production), _name_candidates(
        items[1], kind, production
    )


def _as_token(feat: object) -> str | None:
    """token 元素 → token 名；非 token 元素 → None。"""
    if isinstance(feat, dict) and feat.get("type") == "token":
        return str(feat.get("token_type") or "") or None
    return None


def _prefix_token(feat: object, kind: str, production: str) -> str:
    token_type = _as_token(feat)
    if token_type is None:
        raise ConfigError(
            f"[macro_recognition] {kind} 前缀位须是 token 名 {_PREFIX_FORM}，"
            f"得到: {production!r}"
        )
    parts = token_type.split(".")
    if len(parts) != 3 or parts[0] != "symbol":
        raise ConfigError(
            f"[macro_recognition] {kind} 前缀只支持 {_PREFIX_FORM}，"
            f"得到 {token_type!r}（{production!r}）"
        )
    return token_type


def _name_candidates(feat: object, kind: str, production: str) -> tuple[str, ...]:
    """名字位 → 候选 token 名（空 = 任意标识符）。"""
    token_type = _as_token(feat)
    if token_type is not None:
        if token_type == NAME_TOKEN:
            return ()
        return (_check_candidate(token_type, kind, production),)

    alternatives = feat.get("alternatives") if isinstance(feat, dict) else None
    if feat.get("type") != "choice" or not alternatives:
        raise ConfigError(
            f"[macro_recognition] {kind} 名字位须是 {NAME_TOKEN!r}（任意标识符）或"
            f" token 名候选（如 `macro.define|macro.undef`），得到: {production!r}"
        )
    names: list[str] = []
    for alt in alternatives:
        alt_type = _as_token(alt)
        if alt_type is None:
            raise ConfigError(
                f"[macro_recognition] {kind} 名字位候选须是 token 名（{NAME_TOKEN!r} "
                f"不参与候选），得到: {production!r}"
            )
        names.append(_check_candidate(alt_type, kind, production))
    return tuple(names)


def _check_candidate(token_type: str, kind: str, production: str) -> str:
    """候选名须是 `macro.<关键字>`（指令关键字由去协议前缀推导）。"""
    if not token_type.startswith(MACRO_PREFIX):
        raise ConfigError(
            f"[macro_recognition] {kind} 名字位候选须是 {MACRO_PREFIX}<关键字>"
            f" 形态（指令关键字由去前缀推导），得到 {token_type!r}（{production!r}）"
        )
    return token_type


def _prefix_text(
    token_type: str, kind: str, token_define: dict, skip_undeclared: bool
) -> str | None:
    """前缀 token 名 → 符号文本（取自 token 定义）。

    未声明：调用方自建 token 表（skip_undeclared=True）→ None（跳过该形态）；
    否则 fail-fast（语言包内的名字写错即配置错）。
    """
    _, category, name = token_type.split(".")
    value = ((token_define.get("symbol") or {}).get(category) or {}).get(name)
    if not isinstance(value, str) or not value:
        if skip_undeclared:
            return None
        raise ConfigError(
            f"[macro_recognition] {kind} 前缀 token 名 {token_type!r} 未在 token "
            f"定义中声明（[symbol.{category}] 缺 {name}）"
        )
    return value
