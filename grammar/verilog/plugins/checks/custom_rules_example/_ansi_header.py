"""_ansi_header.py — EX001 非 ANSI 端口声明检查（custom_rules_example，postpass 路径示范）。

判定：模块体出现旧式端口声明（`input a;` 写在 module body 而非模块头
括号内）→ 报 EX001。对应 svlint 的 ANSI 头强制族（references.md 特化
赛道："ANSI 头强制"）。

**这条脚本示范 postpass 路径**（需要整棵树/结构信息时的写法）：
- 入口签名 `run_ansi_header_check(analyzer, context)`——在插件 tpc.toml
  的 `[analyzer] postpasses` 注册，遍历结束后由框架调用；
- AST 从 `analyzer._ast` 取，DFS 用 `iter_children()`；报告走
  `context.report(msg, code=, level=, node=)`；
- 语言知识（Body*Decl 节点名）集中在插件层——与 inst_check
  `_check_inout_tri` 同姿态（[structure] `body_port_rules` 协议是同一
  事实的另一处声明，本范例为可读性直接列出；照抄时可改读协议）。
"""

from core.define import Node

# 模块体端口声明节点（= [structure] body_port_rules 的语言包声明值）
_BODY_PORT_RULES = ("BodyInputDecl", "BodyOutputDecl", "BodyInoutDecl")
# 函数/任务子树整体跳过：其参数与模块体端口同节点名（Body*Decl），
# 但不是模块端口（先例：analyzer/structure.py::_fill_body_ports——旧式
# 函数参数被误当模块端口曾造成 W104 假阳性）。函数参数的 ANSI 风格
# 检查不在本规则范围（要做另起规则）。
_FUNC_OR_TASK = ("FuncDecl", "FuncDeclOld", "TaskDecl", "FunctionDecl",
                 "TaskDeclStmt")


def run_ansi_header_check(analyzer, context) -> None:
    """postpass 入口：遍历本文件 AST，报旧式（非 ANSI）端口声明。

    默认关（规则 default=false）：未进激活集即零开销返回——postpass
    直发诊断不经规则表分发，激活判定须自行查（AW 族同款先例，见
    always_check/_always_check.py）。
    """
    from analyzer.checks import active_rule_ids

    if "EX001" not in active_rule_ids(analyzer):
        return
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, Node):
            if node.node_name in _FUNC_OR_TASK:
                continue  # 函数/任务子树（参数非模块端口）
            if node.node_name in _BODY_PORT_RULES:
                # 一处旧式声明一条——编辑器可逐处跳转/修复
                context.report(
                    "模块使用非 ANSI 端口声明（旧式 body 端口）"
                    "——端口声明建议统一放模块头括号内（ANSI 风格）",
                    code="EX001",
                    level="warning",
                    node=node,
                )
            for child in node.iter_children():
                stack.append(child)
