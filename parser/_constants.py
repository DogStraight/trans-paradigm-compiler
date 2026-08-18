"""parser 包内共享常量。

分层（审计后收敛）：
    - token 类型协议（comment/newline/id）：已集中到 core/token_protocol.py，
      此处 re-export 保持既有 import 路径。
    - COMMENT_NODE_NAME / ROOT_RULE_NAME：**语法规则名**——正常情况从语法树
      推导（parser_core.parse 用 get_block_rule 推导根规则名；block_parser
      从"production == [comment] 的规则"推导注释节点名）。下方值仅作语法树
      无法推导时的最后回退，不是语言知识。
    - BLOCK_NODE_NAME：parser 内部临时容器节点名（parse_block 流程挂语句用，
      随后转移到规则节点，不进入最终 AST）——纯引擎内部名，语法无关。
"""

from core.token_protocol import (
    COMMENT_TOKEN_TYPE,
    IDENTIFIER_TOKEN_TYPE,
    NEWLINE_TOKEN_TYPE,
)

# parser 内部临时块容器节点名（不泄漏到 AST）
BLOCK_NODE_NAME = "Block"

# 语法树无法推导时的回退值（正常路径不依赖）
ROOT_RULE_NAME = "Root"
COMMENT_NODE_NAME = "Comment"
