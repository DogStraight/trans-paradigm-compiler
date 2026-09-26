"""preprocessor/macro_policy.py — 宏处置策略（插件能力）的读取与校验点。

引擎只做**文本操作**（替换 / 锚 / 还原 / 区间记账）；"此处这个宏调用该怎么处置"
是**语言知识** → 由语言包通过既有能力机制声明（`[capabilities] macro_policy =
"file.py:fn"`，与 formatter 同款，见 `core/component_protocol.md`）。

契约（引擎给事实、策略给方案）：

- **call_site**（全是通用文本/位置事实，无语言知识）：`name` / `body` / `is_func` /
  `args_text` / `line` / `col` / `end` / `line_text` / `before` / `after` /
  `at_line_start` / `at_line_end` / `only_call_in_line`。
- **plan**（引擎定义的处置枚举 = 机制面；与铺条目 `mode` 同词，不弄两套名）：
    `splice`  宏体铺进流（+ 宏区间，渲染侧 raw 拼接还原）
    `line`    整行占位（整行换成行注释锚，source_text = 整行原文）
    `inline`  行内注释锚（原位回插宏调用原文）
- 未声明能力 → 默认 `splice`（纯文本替换）；方案非法 → fail-fast（不静默降级）。

能力按 **rules_dir** 作用域查找（该语言包目录下的组件才有资格应答）→
同进程切语言时不串用。

Doc: preprocessor/README.md
"""
from __future__ import annotations

from collections.abc import Callable
from typing import cast

from core.errors import ConfigError

MODE_SPLICE = "splice"
MODE_LINE = "line"
MODE_INLINE = "inline"
MODES: frozenset[str] = frozenset({MODE_SPLICE, MODE_LINE, MODE_INLINE})

# 能力名（语言包 `[capabilities]` 段声明）
CAPABILITY_NAME = "macro_policy"

# 引擎默认方案（未声明策略能力时）：纯文本替换 + 宏区间
DEFAULT_PLAN: dict = {"mode": MODE_SPLICE}


def load_macro_policy(rules_dir: str) -> Callable[[dict], dict] | None:
    """取该语言包的宏处置策略入口（未声明 → None）。

    入口函数返回能力 API 面（dict），其中 `plan` 是策略函数；缺 `plan` → fail-fast。
    """
    from core.plugin_loader import get_capability_in

    entry = get_capability_in(CAPABILITY_NAME, rules_dir)
    if entry is None:
        return None
    api = entry()
    plan = api.get("plan") if isinstance(api, dict) else None
    if not callable(plan):
        raise ConfigError(
            f"[macro_policy] 能力入口须返回含可调用 plan 的表（得到 {type(api).__name__}）"
        )
    return cast(Callable[[dict], dict], plan)  # 已过 callable 检查；签名由能力契约约定


def plan_macro(
    plan_fn: Callable[[dict], dict] | None, call_site: dict
) -> dict:
    """问策略要处置方案；未声明策略 → 默认方案；方案非法 → ConfigError。"""
    if plan_fn is None:
        return DEFAULT_PLAN
    plan = plan_fn(call_site)
    if not isinstance(plan, dict):
        raise ConfigError(
            f"[macro_policy] plan 须返回表（得到 {type(plan).__name__}）：{call_site!r}"
        )
    mode = plan.get("mode")
    if mode not in MODES:
        raise ConfigError(
            f"[macro_policy] plan.mode 须是 {sorted(MODES)} 之一，得到 {mode!r}"
            f"（宏 {call_site.get('name')!r}）"
        )
    return {"mode": mode}
