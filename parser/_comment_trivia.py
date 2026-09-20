"""_comment_trivia.py — 注释位置判定与**通道路由判据**（引擎级单点实现）

三种位置判定，只看 token 序列与行号；token 类型（`space.*` / `newline` /
`comment`）是引擎协议（`_constants.py` 与语言包 token 定义），本模块不含语言知识：

  - `prev_significant_index`：前一**显著** token 下标（跳过 `space.*` / newline /
    comment；无则 -1）
  - `is_line_only`：**独占行**——注释前无同行代码（前遇换行 token / 前一显著
    token 在更早的行 / 文件首）
  - `is_midline`：**行中**——注释后同行还有非注释代码

另含一条**路由判据**（谁消费这条注释）：

  - `comment_leave_to_expression`：`prepare_production` 是否不吞注释、交给被调
    表达式规则（见 `_production.prepare_production` 闸门）

### 注释通道分工与优先级（消费方顺序）

| 位置形态 | 判据 | 消费方（通道） |
|----------|------|----------------|
| 行中（同行前后均有代码） | `is_midline` | `collect_following_comments` → 节点槽 `inline_after` / `inline`（行内原位） |
| 规则内部（非行中；本产生式已匹配元素且锚属本规则） | `comment_leave_to_expression` | 让位闸门 → 表达式入口三分类 → `leading_own_line`（独占行）/ `leading`（行尾） |
| 列表项间（项首元素前） | `production_pointer == 0` | `_repeat_loop` 行号窗口 → 容器上浮为 Comment 迭代项 |
| 容器首元素前/开括号同行 | `_starts_line` + 行号窗口 | `try_plain_rule` → `_claim_head_comments` 领为 Comment 子节点 |
| 其余独占行 | 遇行首/容器窗口边界 | `prepare_production` → line 通道锚条目（restore 兜底 + 宏/条件块 marker 回插） |

前三行是**互斥**的：行中不与另两类重叠；`production_pointer == 0` 与
`comment_leave_to_expression` 互斥（后者要求 `> 0`）。生产侧（`_production`）
与表达式侧（`pratt_parser`）共用本模块。收敛原因（2026-09-17）：同一判定原有
三处实现（`_starts_line` / `_is_line_only_comment` / `pratt_parser._is_own_line`），
且 `space` 子类型匹配范围与"是否跳过注释"语义不一致——同一输入可因路径不同
得到不同分类。
Doc: parser/README.md（注释通道分工）
"""

from ._constants import COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE


def _is_space_token(tok) -> bool:
    """`space` 命名空间下的全部子类型（space / space.fold / space.indent …）。"""
    return tok.type.startswith("space")


def _is_newline_token(tok) -> bool:
    return tok.type == NEWLINE_TOKEN_TYPE


def _is_comment_token(tok) -> bool:
    return tok.type == COMMENT_TOKEN_TYPE


def prev_significant_index(tokens: list, idx: int) -> int:
    """tokens[idx] 之前最近的显著 token 下标（跳过 space.*/newline/comment）。

    无显著 token（文件首或全 trivia）→ -1。
    """
    i = idx - 1
    while i >= 0:
        tok = tokens[i]
        if _is_space_token(tok) or _is_newline_token(tok) or _is_comment_token(tok):
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
        if _is_newline_token(tok):
            return True
        if _is_space_token(tok) or _is_comment_token(tok):
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
        if _is_space_token(tok) or _is_newline_token(tok) or _is_comment_token(tok):
            j += 1
            continue
        return getattr(tok, "line", -1) == line
    return False


def comment_leave_to_expression(
    tokens: list,
    idx: int,
    production_pointer: int,
    production_start_ptr: int,
) -> bool:
    """`prepare_production` 是否**不吞**该注释、交给被调表达式规则处理？

    三条同时成立（与语言无关：只看 token 下标与产生式元素序号）：
      - 注释**非行中**——行中注释（同行前后均有代码）位置在同行，已由
        `collect_following_comments` 走 `inline_after`/`inline`；交给表达式
        入口会被当作"前置"而断行（行内嵌入必须保留）。
      - 本产生式已匹配过元素（`production_pointer > 0`）——注释前有本规则
        已消费的内容、注释后本规则还要继续（`wire A =` 后的注释）。
      - 注释前一个显著 token 属本规则匹配范围（下标 >= `production_start_ptr`）
        ——列表项间/语句间的注释其锚属上一项（`;`/`,`），下标落在起点之前。

    交付后由表达式入口三分类归位：独占行 → `leading_own_line`（硬换行独占
    成行）；行尾 → 右操作数 `leading`（随操作数断行）。就地吞掉则只剩锚点
    插值，而规则内部注释的锚可隔着折叠区几十行，落点必偏（darkriscv 实测）。
    指针/元素信息缺失时保守拒绝（退回原有通道）。
    """
    if is_midline(tokens, idx):
        return False
    if production_pointer <= 0:
        return False
    return prev_significant_index(tokens, idx) >= production_start_ptr
