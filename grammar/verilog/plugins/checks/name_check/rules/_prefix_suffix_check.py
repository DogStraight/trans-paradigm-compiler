"""_prefix_suffix_check.py — 命名前后缀语义约定检查（NC014-016，handler）

L2 脚本 handler（name_check 插件）：前后缀语义约定（防错，2026-08-29
配置面落地）。蓝本 svlint prefix_input/output/inout（require 模式 +
可配置前缀）；tpc 扩展为声明式后缀表 + 类型后缀。规则数据（声明式）：

    [[checks]]  # NC014 端口方向后缀
    kind = "port"
    handler = "_prefix_suffix_check.py:check_direction_suffix"
    direction_suffix = { input = "_i", output = "_o", inout = "_io" }
    # require = true → 未按本方向后缀命名也报（强约定）

    [[checks]]  # NC015/NC016 类型后缀
    kind = "wire" / "reg"
    handler = "_prefix_suffix_check.py:check_kind_suffix"
    kind_suffix = { wire = "_w" } / { reg = "_r" }

判定：
- NC014：名字以配置表中某方向后缀结尾但声明方向不同 → 方向可能接反
  （防错核心，强约束）；require 模式补"未按本方向后缀命名"。
- NC015/016：wire/reg 符号按 kind_suffix 要求命名（require 语义）。

豁免：`_` 前缀（占位/故意不用约定，与 unused_check 同语义）。
不做：`_n` 低有效 / clk_/rst_ 前缀——2005 无 clock/reset 符号 kind，
用途需事件控制/复位条件分析（主流 svlint 亦无，见 ADR-0004「落地演进」）。

签名：fn(symbol, rule, context) -> str | None（None = 通过）。
"""


def check_direction_suffix(symbol, rule, context) -> str | None:
    """端口方向后缀一致性（防接错方向）。"""
    name = getattr(symbol, "name", "") or ""
    if not name or name.startswith("_"):
        return None
    direction = _direction_of(symbol)
    if not direction:
        return None
    table = rule.get("direction_suffix", {}) or {}
    # 后缀 → 方向 反查表（表值应为字符串后缀）
    suffix_dir = {s: d for d, s in table.items() if isinstance(s, str) and s}
    for suffix, dir_of_suffix in suffix_dir.items():
        if name.endswith(suffix) and dir_of_suffix != direction:
            return (
                f"端口 '{name}' 后缀 {suffix} 表示 {dir_of_suffix} 方向"
                f"（声明为 {direction}）——方向可能接反"
            )
    if rule.get("require"):
        own = table.get(direction)
        if isinstance(own, str) and own and not name.endswith(own):
            return f"端口 '{name}' 未按 {direction} 方向后缀约定命名（期望 {own}）"
    return None


def check_kind_suffix(symbol, rule, context) -> str | None:
    """类型后缀一致性（防类型混淆；require 模式补本类型后缀要求）。"""
    name = getattr(symbol, "name", "") or ""
    if not name or name.startswith("_"):
        return None
    kind = getattr(symbol, "kind", "") or ""
    table = rule.get("kind_suffix", {}) or {}
    # 外来类型后缀不匹配（防类型混淆）：名字以其他 kind 的后缀结尾
    for k, s in table.items():
        if k != kind and isinstance(s, str) and s and name.endswith(s):
            return (
                f"信号 '{name}' 后缀 {s} 表示 {k} 类型"
                f"（声明为 {kind}）——类型可能混淆"
            )
    if rule.get("require"):
        own = table.get(kind)
        if isinstance(own, str) and own and not name.endswith(own):
            return f"信号 '{name}' 未按 {kind} 类型后缀约定命名（期望 {own}）"
    return None


def _direction_of(symbol) -> str | None:
    """端口声明方向（decl_node.direction：字符串或关键字 token 节点）。"""
    node = getattr(symbol, "decl_node", None)
    d = getattr(node, "direction", None) if node is not None else None
    if isinstance(d, str):
        return d or None
    if d is not None:
        # 关键字 token 节点（input/output/inout）：value 递归取文本
        for _ in range(4):
            if d is None:
                return None
            c = getattr(d, "content", "") or ""
            if c:
                return c
            v = getattr(d, "value", None)
            if isinstance(v, str):
                return v or None
            if hasattr(v, "node_name"):
                d = v
                continue
            return None
    return None
