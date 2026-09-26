"""when 原语 — 按节点属性值选择布局（同节点名多形态的文本分发）

语言包声明"属性满足条件时用哪一支布局"。引擎零语言知识：属性名、比较值、
两支布局都是数据（同 `suffix_when` 的口径——条件与文本都由布局 TOML 提供）。

典型用途（C 语言包首例）：pratt 产物 `UnaryOp` 用**同一节点名**承载前缀与后缀
（`position = "prefix" | "postfix"`），布局须按 position 选序（`-x` 对 `i++`）。
此前布局原语无"按属性值换序"能力，只能二选一 → `i++` 被渲成 `++i`（token 齐全、
顺序反了；`i++` 与 `++i` 在 C 里语义不同）。

条件词表（一条 `when` 里**恰好一个**条件键）：

| 键 | 语义 |
|---|---|
| `eq` / `ne` | 属性值相等 / 不等 |
| `in` | 属性值在给定列表内 |
| `startswith` | 前缀（与 `suffix_when` 同词表） |
| `exists` | 属性存在与否（真值） |

`then` / `else` 各是一支布局表达式，**可省**（省 = 该分支不输出）。

⚠ 声明形态非法（`when` 非表 / 缺 `attr` / 条件键不是恰好一个 / 条件键不认识）
**直接报 `ConfigError`**，不返回 None：认不出的键会让整块布局**静默输出空串**，
与"缺布局静默丢内容"是同一根因（`renderer/primitives/__init__.py::eval_expr`
对无原语键的字典返回 None）。
Doc: renderer/renderer_architecture.md（布局原语：when 属性分发布局）
"""

from typing import Any
from core.define import Node
from core.errors import ConfigError
from ..doc import Doc
from .registry import register

# 条件键 → 判定；`exists` 单独处理（比较对象是真值而非属性值）
_COMPARE_KEYS = ("eq", "ne", "in", "startswith")
_CONDITION_KEYS = (*_COMPARE_KEYS, "exists")


@register("when")
def eval_when(
    expr: dict, node: Node, parent_layout: dict | None, renderer: Any
) -> Doc | None:
    """按 `when` 条件选支求值：命中取 `then`、否则取 `else`（缺省分支 → None）。"""
    cond = expr.get("when")
    attr, key, want = _parse_condition(cond)
    hit = _hit(key, want, getattr(node, attr, None))
    branch = expr.get("then") if hit else expr.get("else")
    if branch is None:
        return None
    return renderer._eval(branch, node, parent_layout)


def _parse_condition(cond: Any) -> tuple[str, str, Any]:
    """条件表 → (属性名, 条件键, 期望值)；形态非法即 fail-fast。"""
    if not isinstance(cond, dict):
        raise ConfigError(f"when 原语的条件须为表，实得 {cond!r}")
    attr = cond.get("attr")
    if not isinstance(attr, str) or not attr:
        raise ConfigError(
            f"when 原语须声明属性名 attr（字符串），实得 {attr!r}（条件表 {cond!r}）"
        )
    keys = [k for k in _CONDITION_KEYS if k in cond]
    if len(keys) != 1:
        raise ConfigError(
            f"when 原语须**恰好**声明一个条件键（{', '.join(_CONDITION_KEYS)}），"
            f"实得 {keys or '（无）'}（条件表 {cond!r}）"
        )
    return attr, keys[0], cond[keys[0]]


def _hit(key: str, want: Any, val: Any) -> bool:
    """条件判定；属性缺失（None）时除 `exists` 外一律不命中（不报错）。"""
    if key == "exists":
        return (val is not None) == bool(want)
    if val is None:
        return False
    if key == "eq":
        return val == want
    if key == "ne":
        return val != want
    if key == "in":
        return isinstance(want, list) and val in want
    return isinstance(val, str) and val.startswith(str(want))
