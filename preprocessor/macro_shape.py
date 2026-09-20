"""preprocessor/macro_shape.py — 宏形态声明的读取点（语言包 `[macro_recognition]`）。

宏形态用**生产式**表达形状 + **候选列表**表达名字位枚举（引擎只做通用解析，
语言知识不进代码）：

    [macro_recognition]
shape          = "symbol.base.backtick,name"     # 前缀 token 名 + 名字位占位符
        directive      = ["macro.define", "macro.undef", ...]   # 名字位候选（列表枚举）
        call           = []                                     # 空列表 = 任意标识符
        call_args      = "bracket.l_parentheses,args,bracket.r_parentheses"
        arg_separator  = "symbol.base.comma"
        suffix_after_call = "'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*"

- `shape` 是与 grammar rules 同一套规则的生产式（`,` 顺序 / token 名），
  `name` 是**名字位占位符**（引擎在这里扫一个名字）；前缀位写 token 名
  （`symbol.<cat>.<name>`）→ 符号文本取自 token 定义，不在引擎里硬编码语言字符。
- `call_args` / `arg_separator` 是**带参宏的实参形态**：调用括号对（写 bracket
  token 名，文本取自 `[bracket].pairs`）+ 实参槽占位符 `args` + 顶层实参分隔符
  （写 symbol token 名）——定义侧（`` `define NAME(a, b) ``）与调用侧（`` `NAME(x, y) ``）
  同形，共用一份声明。配平计深的括号对 = 语言包声明的**全部**括号对。
- `suffix_after_call` 是**宏调用后随字面量后缀**的形态模式（`` `W'd0 `` → `'d0`）
  ——展开时把后缀纳入调用区间使替换与 token 边界对齐（比 `[[number.based]]`
  宽一档，见 `load_macro_call_suffix`）。
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
import re
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
# 带参实参形态的声明键 + 实参槽占位符（引擎在槽位扫实参列表，按分隔符切分）
CALL_ARGS_KEY = "call_args"
ARG_SEPARATOR_KEY = "arg_separator"
ARGUMENT_SLOT = "args"
_CALL_ARGS_FORM = f'"bracket.l_<名>,{ARGUMENT_SLOT},bracket.r_<名>"'
# 宏调用后随字面量后缀的形态模式键（如 verilog 的 `` `W'd0 `` → "'d0"）
CALL_SUFFIX_KEY = "suffix_after_call"


@dataclass(frozen=True)
class _MacroShape:
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


@dataclass(frozen=True)
class MacroCallArgs:
    """带参宏的括号/分隔符形态（`[macro_recognition]` 声明解析结果）。

    定义侧（`` `define NAME(a, b) body ``）与调用侧（`` `NAME(x, y) ``）同形，
    共用一份声明；`nesting` 是配平计深用的括号对（语言包声明的全部括号对）。
    括号文本按声明**整串**匹配 → 多字符括号对同样适用。
    """

    open: str
    close: str
    separator: str
    nesting: tuple[tuple[str, str], ...]

    def _opener_at(self, text: str, i: int) -> tuple[str, str] | None:
        """位置 i 处的嵌套开括号对 `(open, close)`；无 → None。"""
        return next(
            (p for p in tuple(self.nesting) if text.startswith(p[0], i)), None
        )

    def _closer_at(self, text: str, i: int) -> str | None:
        """位置 i 处的闭括号文本（长串优先）；无 → None。"""
        return next(
            (c for c in _sorted_closers(self.nesting) if text.startswith(c, i)), None
        )

    def match_args(self, text: str, open_idx: int) -> tuple[str, int] | None:
        """从 open_idx（开括号处）配平到对应闭括号 → (内部文本, 闭括号后位置)。

        未配平（未闭合 / 调用跨行）→ None：调用方自行容错（定义侧退化为对象宏、
        展开侧按非带参调用处理）。
        """
        if not text.startswith(self.open, open_idx):
            return None
        inner_start = open_idx + len(self.open)
        expect: list[str] = [self.close]
        i = inner_start
        while i < len(text):
            opener = self._opener_at(text, i)
            if opener is not None:
                expect.append(opener[1])
                i += len(opener[0])
                continue
            closer = self._closer_at(text, i)
            if closer is None:
                i += 1
                continue
            if expect and expect[-1] == closer:
                expect.pop()
                if not expect:
                    return text[inner_start:i], i + len(closer)
            i += len(closer)
        return None

    def split(self, text: str) -> list[str]:
        """按顶层分隔符切分实参（括号对内的分隔符不算），各段去首尾空白。"""
        parts: list[str] = []
        cur: list[str] = []
        depth = 0
        i = 0
        while i < len(text):
            opener = self._opener_at(text, i)
            if opener is not None:
                depth += 1
                cur.append(opener[0])
                i += len(opener[0])
                continue
            closer = self._closer_at(text, i)
            if closer is not None:
                depth -= 1
                cur.append(closer)
                i += len(closer)
                continue
            if depth == 0 and text.startswith(self.separator, i):
                parts.append("".join(cur).strip())
                cur = []
                i += len(self.separator)
                continue
            cur.append(text[i])
            i += 1
        parts.append("".join(cur).strip())
        return parts


def _sorted_closers(nesting: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """全部闭括号（长串优先——`>>` 不被 `>` 抢先匹配）。"""
    return tuple(sorted({c for _, c in nesting}, key=len, reverse=True))


def _require_shape_production(recognition: dict) -> str | None:
    """取 `shape` 生产式：未声明（且无形态段）→ None；缺失/非法 → fail-fast。"""
    shape_production = recognition.get("shape")
    if shape_production is None:
        declared = [k for k in SHAPE_KINDS if recognition.get(k) is not None]
        if declared:
            raise ConfigError(
                f"[macro_recognition] 声明了形态段 {declared} 但缺 shape"
                f"（形态形状写在 shape，如 {_SHAPE_FORM}）"
            )
        return None
    if not isinstance(shape_production, str) or not shape_production.strip():
        raise ConfigError(
            f"[macro_recognition] shape 须是非空生产式字符串（得到 {shape_production!r}）"
        )
    return shape_production


def _shape_prefix(
    shape_production: str, token_define: dict, skip_undeclared: bool
) -> str | None:
    """形态生产式 → 前缀文本（`_PARSE_CACHE` 记忆化；未声明前缀 → None）。"""
    prefix_token = _PARSE_CACHE.get(shape_production)
    if prefix_token is None:
        prefix_token = _parse_shape(shape_production)
        _PARSE_CACHE[shape_production] = prefix_token
    return _prefix_text(prefix_token, token_define, skip_undeclared)


def _declared_shapes(recognition: dict, prefix: str) -> dict[str, _MacroShape]:
    """逐形态段构造 _MacroShape（未声明的段不出现）。"""
    shapes: dict[str, _MacroShape] = {}
    for kind in SHAPE_KINDS:
        value = recognition.get(kind)
        if value is not None:
            shapes[kind] = _MacroShape(
                kind=kind, prefix=prefix, names=_candidates(value, kind)
            )
    return shapes


def load_macro_shapes(
    cfg: dict | None = None,
    token_define: dict | None = None,
    rules_dir: str | None = None,
    *,
    skip_undeclared_prefix: bool = False,
) -> dict[str, _MacroShape]:
    """读取 `[macro_recognition]` → `{kind: _MacroShape}`（未声明的段不出现）。

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
        token_define = _token_define_of(rules_dir)
    token_define = token_define or {}
    recognition = _recognition(cfg)

    shape_production = _require_shape_production(recognition)
    if shape_production is None:
        return {}
    prefix = _shape_prefix(shape_production, token_define, skip_undeclared_prefix)
    if prefix is None:
        return {}
    return _declared_shapes(recognition, prefix)


def macro_keywords(shape: _MacroShape) -> tuple[str, ...]:
    """名字位候选 → 指令关键字（`macro.define` → `define`）。"""
    return tuple(name[len(MACRO_PREFIX):] for name in shape.names)


def load_macro_call_args(
    cfg: dict | None = None,
    token_define: dict | None = None,
    rules_dir: str | None = None,
    *,
    skip_undeclared_prefix: bool = False,
) -> MacroCallArgs | None:
    """读取 `[macro_recognition]` 的带参实参形态（未声明 → None）。

        call_args     = "bracket.l_parentheses,args,bracket.r_parentheses"
        arg_separator = "symbol.base.comma"

    括号对文本按 token 名从 `[bracket].pairs` 取、分隔符文本从 `[symbol.*]` 取
    （引擎不硬编码 `(` / `,`）；配平计深的括号对 = 语言包声明的全部括号对。
    声明非法（形态不是括号对 / 槽名不是 args / 名字未声明 / 缺分隔符）→
    fail-fast（不静默降级）。

    cfg / token_define / rules_dir / skip_undeclared_prefix 语义同
    `load_macro_shapes`。
    """
    if cfg is None:
        cfg = _resolve_macro_cfg(rules_dir) if rules_dir else _macro_cfg
    if token_define is None and rules_dir:
        token_define = _token_define_of(rules_dir)
    token_define = token_define or {}
    recognition = _recognition(cfg)

    production = recognition.get(CALL_ARGS_KEY)
    if production is None:
        return None
    if not isinstance(production, str) or not production.strip():
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 须是非空生产式（{_CALL_ARGS_FORM}），"
            f"得到 {production!r}"
        )
    separator_token = recognition.get(ARG_SEPARATOR_KEY)
    if not isinstance(separator_token, str) or not separator_token:
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 须与 {ARG_SEPARATOR_KEY}"
            f"（实参分隔符 token 名，如 \"symbol.base.comma\"）同时声明，"
            f"得到 {separator_token!r}"
        )

    open_token, close_token = _parse_call_args(production)
    open_text = _token_text(
        open_token, token_define, skip_undeclared_prefix, f"{CALL_ARGS_KEY} 开括号"
    )
    close_text = _token_text(
        close_token, token_define, skip_undeclared_prefix, f"{CALL_ARGS_KEY} 闭括号"
    )
    separator = _token_text(
        separator_token, token_define, skip_undeclared_prefix, ARG_SEPARATOR_KEY
    )
    if open_text is None or close_text is None or separator is None:
        return None
    nesting = _bracket_pairs(token_define)
    if (open_text, close_text) not in nesting:
        nesting = nesting + ((open_text, close_text),)
    return MacroCallArgs(
        open=open_text, close=close_text, separator=separator, nesting=nesting
    )


def _require_suffix_pattern(recognition: dict) -> str | None:
    """取 `suffix_after_call` 形态模式：未声明 → None；非法（非串/空）→ fail-fast。"""
    pattern = recognition.get(CALL_SUFFIX_KEY)
    if pattern is None:
        return None
    if not isinstance(pattern, str) or not pattern.strip():
        raise ConfigError(
            f"[macro_recognition] {CALL_SUFFIX_KEY} 须是非空形态模式字符串"
            "（如 \"'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*\"），"
            f"得到 {pattern!r}"
        )
    return pattern


def _compile_suffix_pattern(pattern: str) -> re.Pattern[str]:
    """编译后缀模式（非合法正则 / 可匹配空串 → fail-fast）。"""
    try:
        compiled = re.compile(f"^(?:{pattern})")
    except re.error as exc:
        raise ConfigError(
            f"[macro_recognition] {CALL_SUFFIX_KEY} 不是合法正则: {pattern!r}（{exc}）"
        ) from exc
    if compiled.match(""):
        raise ConfigError(
            f"[macro_recognition] {CALL_SUFFIX_KEY} 须至少匹配一个字符"
            f"（匹配空串会让扩展区间退化），得到 {pattern!r}"
        )
    return compiled


def load_macro_call_suffix(
    cfg: dict | None = None,
    rules_dir: str | None = None,
) -> re.Pattern[str] | None:
    """读取宏调用后随字面量后缀的**形态模式**（未声明 → None）。

        suffix_after_call = "'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*"

    模式从位置处匹配（引擎按 `^` 锚定，只关心“开头是不是这个后缀”）；
    与 `[literal] number` / `[id.id] id` 同款——形态模式写在语言包，引擎只编译
    不解释。声明的模式比 `[[number.based]]` **宽一档**：还要覆盖无进制字母的
    SV 填充字面量 `` `W'0 `` / `` `W'1 ``，故单独声明（不复用数字形态）。
    声明非法（非串 / 不能编译 / 可匹配空串）→ fail-fast（见 `_require_suffix_pattern`
    与 `_compile_suffix_pattern`）。
    """
    if cfg is None:
        cfg = _resolve_macro_cfg(rules_dir) if rules_dir else _macro_cfg
    recognition = _recognition(cfg)
    pattern = _require_suffix_pattern(recognition)
    if pattern is None:
        return None
    return _compile_suffix_pattern(pattern)


def _recognition(cfg: dict) -> dict:
    """宏配置 → `[macro_recognition]` 表（缺省空表；非表 → fail-fast）。"""
    recognition = cfg.get("macro_recognition") or {}
    if not isinstance(recognition, dict):
        raise ConfigError(
            f"[macro_recognition] 须是表（得到 {type(recognition).__name__}）"
        )
    return recognition


def _token_define_of(rules_dir: str) -> dict:
    """该语言包的 token 定义（与 Lexer(rules_dir=...) 同源）。"""
    from lexer.lexer_utils import get_token_define_merged

    return get_token_define_merged(rules_dir)


def _parse_call_args(production: str) -> tuple[str, str]:
    """call_args 生产式 → (开括号 token 名, 闭括号 token 名)。非法 → ConfigError。"""
    from parser.rule_selector import analyze_production_features

    try:
        feat = analyze_production_features(production)
    except Exception as exc:  # noqa: BLE001 — 生产式语法错误即配置错（fail-fast）
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 无法解析: {production!r}（{exc}）"
        ) from exc

    if not isinstance(feat, dict):
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 无法解析为特征树: {production!r}"
        )
    items = feat.get("items")
    if feat.get("type") != "seq" or not items or len(items) != 3:
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 须是三位顺序 {_CALL_ARGS_FORM}"
            f"（括号对夹一个实参槽），得到: {production!r}"
        )
    open_token, middle, close_token = (
        _as_token(items[0]),
        _as_token(items[1]),
        _as_token(items[2]),
    )
    if middle != ARGUMENT_SLOT:
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 中间位须写 {ARGUMENT_SLOT!r}"
            f"（实参槽占位符），得到: {production!r}"
        )
    if not open_token or not close_token:
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 两侧须写 bracket token 名"
            f"（{_CALL_ARGS_FORM}），得到: {production!r}"
        )
    open_name = _bracket_side_name(open_token, "l_")
    close_name = _bracket_side_name(close_token, "r_")
    if open_name != close_name:
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 括号对名称须一致（开 {open_token!r} "
            f"/ 闭 {close_token!r}）——同名即同一对（[bracket].pairs）"
        )
    return open_token, close_token


def _bracket_side_name(token_type: str, side: str) -> str:
    """`bracket.l_<名>` / `bracket.r_<名>` → `<名>`；形态非法 → ConfigError。"""
    prefix = f"bracket.{side}"
    if not token_type.startswith(prefix) or len(token_type) == len(prefix):
        raise ConfigError(
            f"[macro_recognition] {CALL_ARGS_KEY} 括号位须是 token 名 "
            f"'bracket.{side}<名>'，得到 {token_type!r}"
        )
    return token_type[len(prefix):]


def _bracket_pairs(token_define: dict) -> tuple[tuple[str, str], ...]:
    """语言包声明的括号对（`[bracket].pairs`：开 / 闭 / 名）。"""
    pairs = (token_define.get("bracket") or {}).get("pairs") or []
    out: list[tuple[str, str]] = []
    for item in pairs:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]), str(item[1])))
    return tuple(out)


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

    if not isinstance(feat, dict):
        raise ConfigError(
            f"[macro_recognition] shape 无法解析为特征树: {production!r}"
        )
    items = feat.get("items")
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


def _token_text(
    token_type: str, token_define: dict, skip_undeclared: bool, where: str
) -> str | None:
    """token 名 → 文本（`symbol.<类>.<名>` 或 `bracket.[lr]_<名>`）。

    未声明：token 表由调用方自建（skip_undeclared=True）→ None（跳过该形态）；
    否则 fail-fast（语言包内的名字写错即配置错）。
    """
    parts = token_type.split(".")
    hint = ""
    if len(parts) == 3 and parts[0] == "symbol":
        value = ((token_define.get("symbol") or {}).get(parts[1]) or {}).get(parts[2])
        hint = f"（[symbol.{parts[1]}] 缺 {parts[2]}）"
    elif len(parts) == 2 and parts[0] == "bracket" and parts[1][:2] in ("l_", "r_"):
        side = 0 if parts[1].startswith("l_") else 1
        name = parts[1][2:]
        value = next(
            (
                pair[side]
                for pair in (token_define.get("bracket") or {}).get("pairs") or []
                if isinstance(pair, (list, tuple))
                and len(pair) >= 3
                and pair[2] == name
            ),
            None,
        )
        hint = f"（[bracket].pairs 缺 {name}）"
    else:
        raise ConfigError(
            f"[macro_recognition] {where} 须是 token 名（symbol.<类>.<名> 或 "
            f"bracket.[lr]_<名>），得到 {token_type!r}"
        )
    if not isinstance(value, str) or not value:
        if skip_undeclared:
            return None
        raise ConfigError(
            f"[macro_recognition] {where} token 名 {token_type!r} 未在 token 定义中"
            f"声明{hint}"
        )
    return value


def _prefix_text(
    token_type: str, token_define: dict, skip_undeclared: bool
) -> str | None:
    """前缀 token 名 → 符号文本（取自 token 定义）。

    未声明：调用方自建 token 表（skip_undeclared=True）→ None（跳过该形态）；
    否则 fail-fast（语言包内的名字写错即配置错）。
    """
    return _token_text(token_type, token_define, skip_undeclared, "shape 前缀")
