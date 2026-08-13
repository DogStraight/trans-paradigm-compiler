"""checkers — 扁平检查器集合。

每个检查器只检查一种语法结构，由发现阶段（discovery）注册：
    boundary.py    — 块边界配对（迁移原 P1）
    macro_token.py — 未定义宏等非法 token（迁移原 P0）
    statement.py   — 语句结构（从 production 编译）
    expression.py  — 表达式（借力 parser pratt）
"""
