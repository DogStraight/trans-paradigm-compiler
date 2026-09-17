"""macro_policy 插件 — verilog 宏处置策略。

引擎（`preprocessor/_expand.expand_tokens`）每个宏调用问一次"该怎么处置"，
本插件按语言事实作答（契约见 `preprocessor/README.md`「宏处置策略（插件能力）」；
调用点事实由引擎给，按 mode 枚举回）：

    splice        宏体文本铺进流（check/lint 要宏体语义，不要保真锚）
    line          整行占位（行首空体宏 = decl 修饰符，文本替换会破坏 decl）
    inline        行内注释锚（行内空体宏：替换为空会丢调用原文）

判定与真实语料依据见本插件 README。
Doc: grammar/verilog/plugins/macro_policy/README.md
"""


def plan(call_site: dict) -> dict:
    """宏调用点 → 处置方案（{mode}）。

    优先序与语言事实绑定：**空体宏形态优先**（替换为空会丢调用原文，且行首
    形态会破坏周边 decl）→ 非空体宏体文本铺进流。
    """
    if not call_site.get("body"):
        # 空体宏：替换成空会丢调用原文
        if call_site.get("only_call_in_line") and call_site.get("at_line_start"):
            # 行首空体宏是声明修饰符（`FORMAL_KEEP reg [3:0] q;`）→ 整行占位
            return {"mode": "line"}
        return {"mode": "inline"}

    # 非空体宏：宏体文本铺进流，还原靠宏区间 raw 拼接
    return {"mode": "splice"}


def build_macro_policy() -> dict:
    """能力入口（`[capabilities] macro_policy`）→ 能力 API 面。"""
    return {"plan": plan}
