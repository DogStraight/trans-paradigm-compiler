"""preprocessor/macro_shape.py — 宏形态声明的读取点（语言包 `[macro_recognition]`）。

宏形态用**生产式**表达形状 + **候选列表**表达名字位枚举（引擎只做通用解析，
语言知识不进代码）：

    [macro_recognition]
    shape     = "symbol.base.backtick,name"     # 前缀 token 名 + 名字位占位符
    directive = ["macro.define", "macro.undef", ...]   # 名字位候选（列表枚举）
    call      = []                                     # 空列表 = 任意标识符

- `shape` 是与 grammar rules 同一套规则的生产式（`,` 顺序 / token 名），
  `name` 是**名字位占位符**（引擎在这里扫一个名字）；前缀位写 token 名
  （`symbol.<cat>.<name>`）→ 符号文本取自 token 定义，不在引擎里硬编码语言字符。
- 形态段（directive / call）声明名字位候选：**命中哪个候选就产出哪个 token
  类型**；候选为空列表 = 名字位是任意标识符（产出 `macro.call`，引擎协议常量，
  见 `core/token_protocol.py`）；整段不声明 = 该形态不识别（如 C 的宏调用就是
  普通标识符）。

未实现形态（后缀序 / 非符号前缀 / 多于两位）与非列表候选 → fail-fast
（不静默降级，见 `core/config_lifecycle.md`）。

Doc: preprocessor/README.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from core.config_registry import declare_cfg
from core.errors import ConfigError
from core.token_protocol import MACRO_PREFIX

_macro_cfg: dict = declare_cfg("preprocessor.macro_config", {}, __name__, "_macro_cfg")

# `shape` 生产式 → 前缀 token 名的内容寻址缓存（纯函数）：同一 shape 结果恒定，
# 前缀文本按 token 定义另行解析（token 定义随语言包变）。
# 登记见 core/global_state.py 的 CONTENT_ADDRESSED。
_PARSE_CACHE: dict[str, str] = {}

KIND_DIRECTIVE = "directive"
KIND_CALL = "call"
# 识别顺序：指令段优先（同前缀时指令优先）——lexer 与展开侧共用此顺序。
SHAPE_KINDS: tuple[str, ...] = (KIND_DIRECTIVE, KIND_CALL)
# shape 里的名字位占位符（引擎在此扫一个名字）
NAME_SLOT = "name"
_SHAPE_FORM = '"symbol.<cat>.<name>,name"（前缀 token 名 + 名字位占位符）'


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

        候选写成 token 名（`macro.define`）→ 扫到裸名字 `define` 时按协议前缀
        拼回候选名比对；命中即产出该 token 类型。
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

    shape_production = recognition.get("shape")
    if shape_production is None:
        declared = [k for k in SHAPE_KINDS if recognition.get(k) is not None]
        if declared:
            raise ConfigError(
                f"[macro_recognition] 声明了形态段 {declared} 但缺 shape"
                f"（形态形状写在 shape，如 {_SHAPE_FORM}）"
            )
        return {}
    if not isinstance(shape_production, str) or not shape_production.strip():
        raise ConfigError(
            f"[macro_recognition] shape 须是非空生产式字符串（得到 {shape_production!r}）"
        )

    prefix_token = _PARSE_CACHE.get(shape_production)
    if prefix_token is None:
        prefix_token = _parse_shape(shape_production)
        _PARSE_CACHE[shape_production] = prefix_token
    prefix = _prefix_text(prefix_token, token_define, skip_undeclared_prefix)
    if prefix is None:
        return {}

    shapes: dict[str, MacroShape] = {}
    for kind in SHAPE_KINDS:
        value = recognition.get(kind)
        if value is None:
            continue
        shapes[kind] = MacroShape(
            kind=kind, prefix=prefix, names=_candidates(value, kind)
        )
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


# ── 声明解析（通用，不懂语言） ──


def _parse_shape(production: str) -> str:
    """shape 生产式 → 前缀 token 名。形态非法 → ConfigError。"""
    from parser.rule_selector import analyze_production_features

    try:
        feat = analyze_production_features(production)
    except Exception as exc:  # noqa: BLE001 — 生产式语法错误即配置错（fail-fast）
        raise ConfigError(
            f"[macro_recognition] shape 无法解析: {production!r}（{exc}）"
        ) from exc

    items = feat.get("items") if isinstance(feat, dict) else None
    if feat.get("type") != "seq" or not items or len(items) != 2:
        raise ConfigError(
            f"[macro_recognition] shape 须是两位顺序 {_SHAPE_FORM}，得到: {production!r}"
        )
    first, second = _as_token(items[0]), _as_token(items[1])
    if second != NAME_SLOT:
        if first == NAME_SLOT:
            raise ConfigError(
                "[macro_recognition] shape 后缀序未实现（名字位须在前缀 token "
                f"之后）: {production!r}"
            )
        raise ConfigError(
            f"[macro_recognition] shape 名字位须写 {NAME_SLOT!r}（占位符），"
            f"得到: {production!r}"
        )
    if first is None or not first.startswith("symbol.") or len(first.split(".")) != 3:
        raise ConfigError(
            f"[macro_recognition] shape 前缀位须是 token 名 {_SHAPE_FORM}，"
            f"得到 {first!r}（{production!r}）"
        )
    return first


def _as_token(feat: object) -> str | None:
    """token 元素 → token 名；非 token 元素 → None。"""
    if isinstance(feat, dict) and feat.get("type") == "token":
        return str(feat.get("token_type") or "") or None
    return None


def _candidates(value: object, kind: str) -> tuple[str, ...]:
    """形态段的名字位候选列表 → token 名元组（空列表 = 任意标识符）。"""
    if not isinstance(value, list):
        raise ConfigError(
            f"[macro_recognition] {kind} 须是候选 token 名列表"
            f"（空列表 = 名字位任意标识符），得到 {value!r}"
        )
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ConfigError(
                f"[macro_recognition] {kind} 候选须是 token 名字符串，得到 {item!r}"
            )
        names.append(_check_candidate(item, kind))
    return tuple(names)


def _check_candidate(token_type: str, kind: str) -> str:
    """候选名须是 `macro.<关键字>`（指令关键字由去协议前缀推导）。"""
    if not token_type.startswith(MACRO_PREFIX):
        raise ConfigError(
            f"[macro_recognition] {kind} 候选须是 {MACRO_PREFIX}<关键字> 形态"
            f"（指令关键字由去前缀推导），得到 {token_type!r}"
        )
    return token_type


def _prefix_text(
    token_type: str, token_define: dict, skip_undeclared: bool
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
            f"[macro_recognition] shape 前缀 token 名 {token_type!r} 未在 token "
            f"定义中声明（[symbol.{category}] 缺 {name}）"
        )
    return value
