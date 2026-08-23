"""core/token_protocol.py — 引擎级 token 类型命名协议（单一事实源）。

lexer 产出的 token 类型遵循统一命名协议，所有消费方必须引用本模块的
常量/构造函数，禁止散落字符串拼接：

    前缀 + 名字
    ────────────────────────────────────────────
    keyword.<name>        关键字 token（语言知识在 <name>，前缀是协议）
    symbol.<cat>.<name>   符号 token（cat = base/extend 等类别）
    bracket.l_<name>      左括号 / 右括号（name 来自 [bracket].pairs）
    bracket.r_<name>
    space.<name>          空白（blank/tab/fold/indent/dedent）
    literal.<name>        字面量（number/string/...）
    macro.<name>          预处理宏 token（directive 名 → macro.<name>）
    comment / newline / id  无前缀的引擎基础 token（见下方具体常量）

前缀是**引擎协议**（lexer 按此产出、下游按此消费），不是语言知识——
语言知识是 keyword.module 这类具体名字。
"""

# ── 前缀常量 ──
KEYWORD_PREFIX = "keyword."
SYMBOL_PREFIX = "symbol."
BRACKET_L_PREFIX = "bracket.l_"
BRACKET_R_PREFIX = "bracket.r_"
SPACE_PREFIX = "space."
LITERAL_PREFIX = "literal."
MACRO_PREFIX = "macro."


# ── 构造函数 ──
def keyword_type(name: str) -> str:
    return f"{KEYWORD_PREFIX}{name}"


def symbol_type(category: str, name: str) -> str:
    return f"{SYMBOL_PREFIX}{category}.{name}"


def bracket_types(name: str) -> tuple[str, str]:
    return f"{BRACKET_L_PREFIX}{name}", f"{BRACKET_R_PREFIX}{name}"


def bracket_left(name: str) -> str:
    return f"{BRACKET_L_PREFIX}{name}"


def bracket_right(name: str) -> str:
    return f"{BRACKET_R_PREFIX}{name}"


def literal_type(name: str) -> str:
    return f"{LITERAL_PREFIX}{name}"


def macro_type(name: str) -> str:
    return f"{MACRO_PREFIX}{name}"


# ── 引擎基础 token 类型（lexer 产出、无前缀） ──
# 这些是引擎协议而非语言知识：lexer 代码按此产出（set_type 写死），
# 下游（parser/linter）按此消费。语言层通过 token 定义配置触发产出，
# 不改类型名。
COMMENT_TOKEN_TYPE = "comment"
NEWLINE_TOKEN_TYPE = "newline"
IDENTIFIER_TOKEN_TYPE = "id"

# trivia token 类型集合（空白/折叠/注释/换行）：linter/parser 跳过用。
# 单一事实源——历史曾在 linter 4 个文件各定义一份（A8 去重）。
TRIVIA_TOKEN_TYPES = frozenset(
    {"space.fold", "space", COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE}
)
