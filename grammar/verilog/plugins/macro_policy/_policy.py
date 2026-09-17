"""macro_policy 插件 — verilog 宏处置策略。

引擎（`preprocessor/_expand.expand_tokens`）每个宏调用问一次"该怎么处置"，
本插件按语言事实作答（契约见 `preprocessor/README.md`「宏处置策略（插件能力）」；
调用点事实由引擎给，按 dispositions 枚举回）：

    splice        宏体文本铺进流（check/lint 要宏体语义，不要锚）
    line          整行占位（行首空体宏 = decl 修饰符，token 替换会破坏 decl）
    inline        行内注释锚（空体宏：token 替换会留相邻原子）
    token         唯一 token 锚（独占一行的语句体宏补分号 → 裸任务调用可解析）

判定与真实语料依据见本插件 README。
Doc: grammar/verilog/plugins/macro_policy/README.md
"""


def plan(call_site: dict) -> dict:
    """宏调用点 → 处置方案（{mode[, append]}）。

    优先序与语言事实绑定：**空体宏形态优先**（它们在任何模式下都靠锚保留调用原文）
    → 非空体宏再看 semantic（语义展开）→ 否那么看是否独占一行（补分号）。
    """
    if not call_site.get("body"):
        # 空体宏：替换成空会丢调用原文（且 token 替换会造相邻原子）
        if call_site.get("only_call_in_line") and call_site.get("at_line_start"):
            # 行首空体宏是声明修饰符（`FORMAL_KEEP reg [3:0] q;`）→ 整行占位
            return {"mode": "line"}
        return {"mode": "inline"}

    if call_site.get("semantic"):
        # 语义展开（check/lint 路径）：宏体铺进流，还原靠宏区间 raw 拼接
        return {"mode": "splice"}

    if call_site.get("at_line_start") and call_site.get("at_line_end"):
        # 独占一行的语句体宏（ice40 cells_sim 的 `SB_DFF_INIT 等）原文常无分号：
        # 锚名是标识符，裸标识符不是合法语句 → 补分号（锚还原按锚名整串匹配，
        # 分号只进替换文本）
        return {"mode": "token", "append": ";"}
    # 行内/表达式位宏：token 锚，随 AST 确定位置，还原精确
    return {"mode": "token"}


def build_macro_policy() -> dict:
    """能力入口（`[capabilities] macro_policy`）→ 能力 API 面。"""
    return {"plan": plan}
