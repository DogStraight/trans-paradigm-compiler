"""preprocessor/macro_shape.py — 宏体形态声明的读取点（语言包 `[macro_shape]`）。

宏体形态是**语言语法知识**（哪些前导符号属于哪类形态），声明在语言包；
引擎只按声明选展开/还原路径（语言知识不进代码）。

当前唯一形态声明 = `suffix_leads`（赋值后缀宏体前导集，消费点
`_expand.py` 的锚形态选择）。

历史注记：曾有的「包装解析形态分类器」（`wrappers` 包裹模板 + `continue_leads`
首 token 预过滤 → 提取 `MacroCall._macro_body` 子树）已删除——其产物无任何
读取者：pipeline 恒以 `semantic=True` 展开（非空体宏不建 token 锚）→
`_stage_macro_nodes` 的锚表恒空 → 该链永不触发。删除判据：A1 无引用。

Doc: preprocessor/README.md
"""
from __future__ import annotations

from core.config_registry import declare_cfg

_shape_cfg: dict = declare_cfg("preprocessor.macro_shape", {}, __name__, "_shape_cfg")


def get_suffix_leads(cfg: dict | None = None) -> tuple[str, ...]:
    """读取"赋值后缀宏体"的前导符号集（语言包 `[macro_shape] suffix_leads`）。

    宏体以此类符号开头（如 verilog 端口默认值宏 `= 1'b1`）→ 展开侧改走
    "行内锚 + body 区间"还原（token 替换会造出相邻原子不可解析）。判定依据是
    **语言语法知识**（哪些前导符号属于赋值后缀形态）→ 声明在语言包；未声明
    或空 → 该处置不启用（该语言无此宏形态）。
    """
    cfg = _shape_cfg if cfg is None else cfg
    return tuple(str(lead) for lead in (cfg.get("suffix_leads") or []))
