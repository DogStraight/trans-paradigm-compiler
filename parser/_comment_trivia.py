"""_comment_trivia.py — 注释/琐碎 token 的位置判定（引擎级单点实现）

三种判定，只看 token 序列与行号；token 类型（`space.*` / `newline` / `comment`）
是引擎协议（`_constants.py` 与语言包 token 定义），本模块不含语言知识。

  - `prev_significant_index`：前一**显著** token 下标（跳过 `space.*` / newline /
    comment；无则 -1）
  - `is_line_only`：**独占行**——注释前无同行代码（前遇换行 token / 前一显著
    token 在更早的行 / 文件首）
  - `is_midline`：**行中**——注释后同行还有非注释代码

生产侧（`_production` 的行首判定与注释让位闸门）与表达式侧（`pratt_parser`
的三分类挂载）共用本模块。收敛原因（2026-09-17）：同一判定原有三处实现
（`_starts_line` / `_is_line_only_comment` / `pratt_parser._is_own_line`），
且 `space` 子类型匹配范围与"是否跳过注释"语义不一致——同一输入可因路径不同
得到不同分类。
Doc: parser/README.md（注释通道分工）
"""

from ._constants import COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE


def is_space_token(tok) -> bool:
    """`space` 命名空间下的全部子类型（space / space.fold / space.indent …）。"""
    return tok.type.startswith("space")


def is_newline_token(tok) -> bool:
    return tok.type == NEWLINE_TOKEN_TYPE


def is_comment_token(tok) -> bool:
    return tok.type == COMMENT_TOKEN_TYPE


def prev_significant_index(tokens: list, idx: int) -> int:
    """tokens[idx] 之前最近的显著 token 下标（跳过 space.*/newline/comment）。

    无显著 token（文件首或全 trivia）→ -1。
    """
    i = idx - 1
    while i >= 0:
        tok = tokens[i]
        if is_space_token(tok) or is_newline_token(tok) or is_comment_token(tok):
            i -= 1
            continue
        return i
    return -1


def is_line_only(tokens: list, idx: int) -> bool:
    """tokens[idx] 是否行首独占（其前无同行代码）。

    行首语义 = 向前扫描遇换行 token，或前一显著 token 落在更早的行，或文件首。
    注释与空白一并跳过（`( // head\\n input` 的 `input` 前是已吞注释 token）。
    """
    i = idx - 1
    while i >= 0:
        tok = tokens[i]
        if is_newline_token(tok):
            return True
        if is_space_token(tok) or is_comment_token(tok):
            i -= 1
            continue
        return getattr(tok, "line", -1) != getattr(tokens[idx], "line", -2)
    return True


def is_midline(tokens: list, idx: int) -> bool:
    """tokens[idx] 之后同行是否还有非注释代码（行中注释判定）。"""
    line = getattr(tokens[idx], "line", -2)
    j = idx + 1
    while j < len(tokens):
        tok = tokens[j]
        if is_space_token(tok) or is_newline_token(tok) or is_comment_token(tok):
            j += 1
            continue
        return getattr(tok, "line", -1) == line
    return False
