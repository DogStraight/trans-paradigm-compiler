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
Doc: core/component_protocol.md（token 类型协议）
"""

import hashlib

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


# ── 宏展开锚名协议（引擎级，语言无关） ──
# 展开阶段把宏调用替换为"锚名"占位。锚名以文本形态出现时带宏前缀
# （`` `<锚名> ``），lexer 依既有宏识别规则归为 macro.call——不为锚新造
# 词法形态（lex 阶段本就能识别宏，做锚时直接改 token 类别即可）。
# 命名空间 __tpc_ 为引擎保留（用户代码不得使用）。锚名 = 保留前缀 +
# 标记词 + 盐 + 序号：
#   - 盐 = 源文本摘要（8 位十六进制）→ 不同文件锚名不同，用户宏体/脚本文本
#     偶然撞名的概率可忽略（锚点必须"别人撞不出来"）；
#   - 序号 = 本次展开内递增 → 同一文件内锚名互不相同；
#   - 用 sha256 而非内置 hash()：PYTHONHASHSEED 随机化会破坏跨进程可复现
#     （同一输入两次运行须得同一锚名，否则还原/对拍不可复现）。
RESERVED_PREFIX = "__tpc_"
ANCHOR_MARK = "marker"


def anchor_salt(source: str) -> str:
    """源文本摘要盐（8 位十六进制）：同源文本 → 同锚名，跨进程可复现。"""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]


def anchor_name(seq: int, salt: str) -> str:
    """锚名：保留前缀 + 标记词 + 盐 + 序号（唯一、可复现、用户写不出）。"""
    return f"{RESERVED_PREFIX}{ANCHOR_MARK}_{salt}_{seq}"


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
