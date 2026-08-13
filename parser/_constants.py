"""parser 包内共享的 token/节点名常量（语言约定集中管理）。

这些字符串本质是目标语言的词法/AST 约定（如 Verilog 的 "comment"/"id"）。
集中在此便于替换语言时统一调整，避免散落各模块的魔法字符串。
"""

# 根规则名（语法 TOML 中 [Root] 定义，作为整个文件的块入口）
ROOT_RULE_NAME = "Root"

# 注释 / 换行 token 类型（词法约定）
COMMENT_TOKEN_TYPE = "comment"
NEWLINE_TOKEN_TYPE = "newline"

# 注释 / 块 节点名（AST 约定）
COMMENT_NODE_NAME = "Comment"
BLOCK_NODE_NAME = "Block"

# 标识符 token 类型（词法约定）
IDENTIFIER_TOKEN_TYPE = "id"
