"""linter 包内共享常量（token 命名约定集中管理）。

这些字符串本质是目标语言的词法约定（如 Verilog 的 "comment" / "bracket."）。
集中在此便于替换语言时统一调整，避免散落各模块的魔法字符串。
"""

# 空白 / 注释 token 类型（trivia）——扫描时跳过
TRIVIA = frozenset({"space.fold", "space", "comment", "newline"})

# token 命名约定前缀
BRACKET_TOKEN_PREFIX = "bracket."
MACRO_TOKEN_PREFIX = "macro."

# 语句终止 token 类型
SEMICOLON_TOKEN_TYPE = "symbol.base.semicolon"
NEWLINE_TOKEN_TYPE = "newline"

# 字面量 / 标识符 token 类型
NUMBER_TOKEN_TYPE = "literal.number"
IDENTIFIER_TOKEN_TYPE = "id"
