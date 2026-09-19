"""indent.py — 缩进重排 pass

基于 boundary 的 scope_depth 重算每行缩进。只改行首空白，不碰 token
（保证 token 完整性：不丢不增）。

规则：
  - 块头行（block_header_of 非空：module/begin/case 等入口行）缩进到"块所在层级"
    （depth - 1），使其与配对 end/endcase 对齐；链式行（end else begin 等）同理。
  - 其余行（普通语句 / end / endcase / endmodule）按 depth 缩进。
"""

from __future__ import annotations

from ..boundary import LineContext
from ..style import line_indent_width

# 条件编译指令行（`ifdef/`ifndef/`else/`elsif/`endif`）：PicoRV32 风格顶格，
# 不随代码块缩进（gen 原始即顶格，indent 按 depth 重算会破坏）。
_IFDEF_DIRECTIVE = ("`ifdef", "`ifndef", "`else", "`elsif", "`endif")


def run_indent_pass(
    lines: list[str],
    contexts: list[LineContext],
    indent_width: int = 4,
) -> list[str]:
    result = list(lines)
    comment = _CommentShifter()
    # contexts 必须**按源行序**遍历：多行块注释的内部段 ctx 在 boundary 里先于
    # 首行 ctx 产出（拆分时先吐内部行），而注释平移量读首行的最终缩进。
    contexts = sorted(contexts, key=lambda c: c.line_number)
    by_line = _contexts_by_line(contexts)
    for idx, ctx in enumerate(contexts):
        # 用 line_number 定位行（1-based），防御 contexts 与行索引错位
        ln = ctx.line_number - 1
        if ln < 0 or ln >= len(result):
            continue
        stripped = result[ln].lstrip()
        if not stripped:
            continue  # 空行 / 纯空白保持
        if ctx.is_comment_cont:
            result[ln] = comment.rewrite(lines, result, ln, stripped)
            continue
        comment.reset()
        if stripped.startswith(_IFDEF_DIRECTIVE):
            result[ln] = stripped
            continue
        if stripped.startswith("`define"):
            continue  # define 保留原缩进（preprocessor 还原含嵌套层级）
        prev = contexts[idx - 1] if idx > 0 else None
        target = _indent_target(ctx, prev, by_line, result, indent_width)
        result[ln] = " " * (target * indent_width) + stripped
    return result


# ── 跨行块注释平移 ──


class _CommentShifter:
    """跨行块注释的整体平移量。

    注释内部段（`is_comment_cont`）保留源相对对齐（` * ` 与 `/*` 对齐是注释
    自身版式），只随注释首行平移——按 scope_depth 重算会把 ` *` 前的对齐空格
    吃掉（实测版权头变成 `* ...`）。
    """

    def __init__(self) -> None:
        self.indent: int | None = None  # 块首行缩进（`*` 开头内部段对齐到它 + 1）
        self.shift: int | None = None  # 自由文本内部段的整体平移量

    def reset(self) -> None:
        """离开注释内部段（本行非 is_comment_cont）时清空。"""
        self.indent = None
        self.shift = None

    def rewrite(
        self, lines: list[str], result: list[str], ln: int, stripped: str
    ) -> str:
        """按注释自身惯例规范化内部段 ln。

        - 内部行以 `*` 开头（`/* * */` 风格）：对齐到**块首行**缩进 + 1（星号
          对齐首行 `/*` 的星号）。与源内相对偏移无关：渲染端对注释是逐字输出
          （首行随布局缩进、内部行仍是源缩进），偏移信息已不可靠，只能按惯例规范。
        - 其余（自由文本，如 ASCII 图）：按首行平移量整体平移，保自身版式。
        """
        if self.indent is None:
            self.indent = line_indent_width(result[ln - 1]) if ln > 0 else 0
        if stripped.startswith("*"):
            return " " * (self.indent + 1) + stripped
        if self.shift is None:
            self.shift = (
                line_indent_width(result[ln - 1]) - line_indent_width(lines[ln - 1])
                if ln > 0
                else 0
            )
        return " " * max(0, line_indent_width(lines[ln]) + self.shift) + stripped


# ── 单行目标缩进 ──


def _contexts_by_line(contexts: list[LineContext]) -> dict[int, LineContext]:
    """line_number → ctx（**首个命中优先**，与旧线性扫描同语义）。

    供续行回查语句头（`multi_header_line`）用，避免每行扫一遍 contexts。
    """
    index: dict[int, LineContext] = {}
    for ctx in contexts:
        index.setdefault(ctx.line_number, ctx)
    return index


def _indent_target(
    ctx: LineContext,
    prev: LineContext | None,
    by_line: dict[int, LineContext],
    result: list[str],
    indent_width: int,
) -> int:
    """本行的目标缩进层级（0 = 顶格）。

    分支优先级即语义：端口列表结束行 → 单语句体悬挂 → 续行 → case 分支项 →
    块头/尾行 → 其余按 scope_depth。注释行不保留原缩进——实例化端口列表内的
    注释行是续行链一员（boundary 的 is_pure_comment 不打断 multi_active），走
    续行缩进（hdr+1）与端口行对齐；独立注释行按 scope_depth 缩进。
    """
    if ctx.port_list_end:
        return 0  # 模块端口列表结束行（`);`）→ 对齐模块头（0 级）
    if _hangs_under_prev(ctx, prev, by_line):
        assert prev is not None  # _hangs_under_prev 已保证 prev 非 None
        return _hanging_level(prev, result, indent_width)
    if ctx.multi_line_cont:
        return _continuation_level(ctx, result, indent_width)
    if ctx.is_case_item and ctx.block_header_of is None and ctx.block_footer_of is None:
        return ctx.scope_depth + 1  # 无 begin 的 case 分支项（`3'b010,`/`default:`）
    if ctx.block_header_of is not None:
        # 块头行：与配对 end 对齐（end 已在 pop 后处于父级深度）
        return max(0, ctx.scope_depth - 1)
    return ctx.scope_depth


def _hangs_under_prev(
    ctx: LineContext, prev: LineContext | None, by_line: dict[int, LineContext]
) -> bool:
    """本行是否为上一行"无 begin 的单语句头"的体（→ 悬挂 +1）。

    上一行是无 begin 的语句头（如 `if (X)` / `for (...)`）→ 本行是其单语句体
    加一级（匹配 PicoRV32/ref 风格）；嵌套单语句头（`if (A)` 后接 `if (B)`）也
    悬挂；else 链行（行首 else）与块头/尾行（begin/end/endcase）走各自逻辑，
    不悬挂。ifdef 块内内容继承悬挂由独立 ifdef pass 处理（indent 不跨指令行）。
    """
    if prev is None:
        return False
    if (
        ctx.is_else_header
        or ctx.block_header_of is not None
        or ctx.block_footer_of is not None
    ):
        return False
    return _is_single_stmt_body(prev, by_line)


def _is_single_stmt_body(prev: LineContext, by_line: dict[int, LineContext]) -> bool:
    """prev 行是否为"无 begin 的单语句头"（其下一行是该头挂的单语句体）。

    多行 if 条件（`if (A &&\\n B)`）：续行本身 sst=False，但语句头是
    single_stmt_header——续行的下一行（单语句体）仍应悬挂，故按
    `multi_header_line` 回查语句头的 sst。
    """
    if prev.single_stmt_header:
        return True
    # 排除续行是块头（`B) begin`）——其下一行是块体，不悬挂。
    if not (
        prev.multi_line_cont and prev.multi_header_line and prev.block_header_of is None
    ):
        return False
    header = by_line.get(prev.multi_header_line)
    return header is not None and header.single_stmt_header


def _hanging_level(prev: LineContext, result: list[str], indent_width: int) -> int:
    """悬挂层级：相对上一行实际缩进 +1（嵌套单语句头可累积 if(a)→if(b)→stmt）。

    prev 是续行（多行 if 条件）时，用**语句头**缩进 +1——续行本身已 +1，再相对
    续行 +1 会多一级（单语句体应相对 if 头 +1，非续行 +1）。
    """
    if prev.multi_line_cont and prev.multi_header_line:
        prev_ln = prev.multi_header_line - 1
    else:
        prev_ln = prev.line_number - 1
    return line_indent_width(result[prev_ln]) // indent_width + 1


def _continuation_level(
    ctx: LineContext, result: list[str], indent_width: int
) -> int:
    """多行语句续行：相对语句头实际缩进 +1（同语句内续行同级，不累积）。

    语句头行尾 `=` 的三目链续行（multi_extra）额外 +1（ref 用 +2）。
    """
    hdr_level = line_indent_width(result[ctx.multi_header_line - 1]) // indent_width
    return hdr_level + 1 + (1 if ctx.multi_extra else 0)
