"""_filename_check.py — 模块名-文件名一致性检查（NC011，handler 兜底）。

L2 脚本 handler（name_check 插件）：跨文件易错点——模块名与源文件名
不一致（svlint module-filename 规则蓝本）。pattern 正则表达不了"文件
上下文"，故走 handler：读符号的 decl_node._file（ProjectChecker 注入）
判定 模块名 == 文件名（去扩展名）。

防御边界：
- 无文件上下文（单文件 analyze / run_pipeline 路径未挂 _file）→ 返回
  None（通过，不误报——文件级检查在 tpc check 场景才有意义）。
- 多模块同文件：只要任一模块名与文件名一致即视为"文件命名正确"，其余
  模块不报（常见形态：模块 + 同名 testbench/包装同文件）；全部模块都
  与文件名不一致才逐个报（文件整体命名错误）。
- 消息自管（handler 返回完整文本，不走引擎 {var} 插值——file_base 不在
  声明式插值表）。

签名：fn(symbol, rule, context) -> str | None（None = 通过）。
"""

import os


def check_module_filename(symbol, rule, context) -> str | None:
    """模块名与文件名一致性判定。"""
    node = getattr(symbol, "decl_node", None)
    fpath = getattr(node, "_file", None)
    if not fpath:
        return None  # 无文件上下文（单文件 analyze），跳过
    file_base = os.path.splitext(os.path.basename(fpath))[0]
    name = getattr(symbol, "name", "") or ""
    if not name:
        return None
    if name == file_base:
        return None
    # 多模块同文件防御：文件里已有模块名 == 文件名 → 该文件命名正确
    if _file_has_matching_module(context, file_base):
        return None
    return f"模块名 '{name}' 与文件名不一致（期望 {file_base}）"


def _file_has_matching_module(context, file_base: str) -> bool:
    """检查全工程模块表里是否有模块名与文件名一致（多模块同文件防御）。

    注意：module_index 是全工程索引（跨文件）。此处语义 = "工程里存在
    名为 file_base 的模块"——若本文件内的模块都不匹配文件名，但工程其他
    文件有同名模块，则不误报本文件（模块可能在拆分的同名文件里）。
    """
    module_index = context.extra.get("module_index") or {}
    return file_base in module_index
