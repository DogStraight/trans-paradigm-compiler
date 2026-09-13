"""_param_type.py — EX002 参数 integer 类型提示（custom_rules_example，handler 路径示范）。

判定：parameter 声明的类型位（`ParamDeclStmt.param_integer`，语法绑定
`keyword.integer?`）存在 → 报。蓝本 svlint `parameter_type_twostate`
的 1364 语境变体（integer 为 4-state、位宽随实现；SV 环境可扩类型表）。

**这条脚本示范 handler 路径**（单符号上下文足够时的写法）：
- 签名 `check_param_type(symbol, rule, context) -> str | None`
  （None = 通过；返回文本 = 诊断消息，引擎统一 {name} 插值后报告）；
- 由 rules/*.toml 的 `handler = "本文件:函数"` 声明；
- 声明节点经 `symbol.decl_node` 拿到（= ParamDeclStmt），类型位读节点
  属性——注意 `getattr` 给缺省（无该槽的声明不报），不要 `hasattr` 链。
"""


def check_param_type(symbol, rule, context) -> str | None:
    """parameter 类型位判定：integer → 提示；其余类型/无类型 → 通过。"""
    del rule, context  # 判定不消费规则字段与上下文（单符号上下文足够）
    node = getattr(symbol, "decl_node", None)
    if node is None:
        return None
    if getattr(node, "param_integer", None) is None:
        return None  # 非 integer 形态（[range]/无类型/其它）→ 通过
    return "参数 '{name}' 使用 integer 类型（4-state、位宽随实现）——建议显式位宽 [msb:lsb]"
