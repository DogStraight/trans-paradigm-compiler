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


def run_indent_pass(
    lines: list[str],
    contexts: list[LineContext],
    indent_width: int = 4,
) -> list[str]:
    result = list(lines)
    # 跨行块注释的**整体平移量**：注释内部段（`is_comment_cont`）保留源相对
    # 对齐（` * ` 与 `/*` 对齐是注释自身版式），只随注释首行平移——按
    # scope_depth 重算会把 ` *` 前的对齐空格吃掉（实测版权头变成 `* ...`）。
    # 平移量读首行的最终缩进，因此 contexts 必须**按源行序**遍历：多行块注释
    # 的内部段 ctx 在 boundary 里先于首行 ctx 产出（拆分时先吐内部行）。
    comment_indent: int | None = None
    comment_shift: int | None = None
    contexts = sorted(contexts, key=lambda c: c.line_number)
    # 条件编译指令行（`ifdef/`ifndef/`else/`elsif/`endif）：PicoRV32 风格顶格，
    # 不随代码块缩进（gen 原始即顶格，indent 按 depth 重算会破坏）
    # ifdef/else/endif 是条件块边界 → 顶格；`define 行保留原缩进（preprocessor
    # 还原的原文已含 ifdef 嵌套缩进，ref 里嵌套 define 有 2/4 空格——重算会
    # 按 scope_depth（模块外=0）顶格，丢失嵌套层级）。
    _IFDEF_DIRECTIVE = ("`ifdef", "`ifndef", "`else", "`elsif", "`endif")
    for idx, ctx in enumerate(contexts):
        # 用 line_number 定位行（1-based），防御 contexts 与行索引错位
        ln = ctx.line_number - 1
        if ln < 0 or ln >= len(result):
            continue
        stripped = result[ln].lstrip()
        if not stripped:
            continue  # 空行 / 纯空白保持
        if getattr(ctx, "is_comment_cont", False):
            # 跨行块注释内部段：**按注释自身惯例规范化**——
            #   - 内部行以 `*` 开头（`/* * */` 风格）：对齐到**块首行**缩进 + 1
            #     （星号对齐首行 `/*` 的星号）。与源内相对偏移无关：渲染端对注释
            #     是逐字输出（首行随布局缩进、内部行仍是源缩进），偏移信息已不
            #     可靠，只能按惯例规范。
            #   - 其余（自由文本，如 ASCII 图）：按首行平移量整体平移，保自身版式。
            if comment_indent is None:
                comment_indent = _indent_chars(result[ln - 1]) if ln > 0 else 0
            if stripped.startswith("*"):
                result[ln] = " " * (comment_indent + 1) + stripped
                continue
            if comment_shift is None:
                prev_ln = ln - 1
                if prev_ln >= 0:
                    comment_shift = _indent_chars(result[prev_ln]) - _indent_chars(
                        lines[prev_ln]
                    )
                else:
                    comment_shift = 0
            result[ln] = " " * max(0, _indent_chars(lines[ln]) + comment_shift) + stripped
            continue
        comment_shift = None
        comment_indent = None
        if stripped.startswith(_IFDEF_DIRECTIVE):
            result[ln] = stripped
            continue
        if stripped.startswith("`define"):
            continue  # define 保留原缩进（preprocessor 还原含嵌套层级）
        # 注释行不保留原缩进：实例化端口列表内的注释行是续行链一员
        # （boundary 的 is_pure_comment 不打断 multi_active），走续行缩进
        # （hdr+1）与端口行对齐；独立注释行按 scope_depth 缩进
        # 单语句体悬挂：上一行是无 begin 的语句头（如 `if (X)` / `for (...)`），
        # 本行是其单语句体 → +1（匹配 PicoRV32/ref 风格）。嵌套单语句头（如
        # `if (A)` 后接 `if (B)`）也悬挂；else 链行（行首 else）与 if/end 对齐不
        # 悬挂。begin/end/endcase 等块头尾行走各自逻辑（block_header/footer）。
        # ifdef 块内内容继承悬挂由独立 ifdef pass 处理（indent 不跨指令行）
        # 多行 if 条件（`if (A &&\n B)`）：续行本身 sst=False，但语句头是
        # single_stmt_header——续行的下一行（单语句体）仍应悬挂。查语句头
        # （multi_header_line）的 sst 继承。
        prev = contexts[idx - 1] if idx > 0 else None
        prev_is_sst = False
        if prev is not None:
            if prev.single_stmt_header:
                prev_is_sst = True
            elif (
                prev.multi_line_cont
                and prev.multi_header_line
                and prev.block_header_of is None
            ):
                # 续行：查语句头是否 single_stmt_header（多行 if 条件的单语句体）。
                # 排除续行是块头（`B) begin`）——其下一行是块体，不悬挂。
                for p in contexts:
                    if p.line_number == prev.multi_header_line:
                        prev_is_sst = p.single_stmt_header
                        break
        hanging = (
            prev is not None
            and prev_is_sst
            and not ctx.is_else_header
            and ctx.block_header_of is None
            and ctx.block_footer_of is None
        )
        # 无 begin 的 case 分支项（如 `3'b010,` / `default:`）→ case+1 级
        case_item_hang = (
            ctx.is_case_item
            and ctx.block_header_of is None
            and ctx.block_footer_of is None
        )
        if ctx.port_list_end:
            # 模块端口列表结束行（`);`）→ 对齐模块头（0 级）
            target = 0
        elif hanging:
            # 相对上一行实际缩进 +1（嵌套单语句头可累积，如 if(a)→if(b)→stmt）。
            # prev 是续行（多行 if 条件）时，用语句头缩进 +1——续行本身已 +1，
            # 再相对续行 +1 会多一级（单语句体应相对 if 头 +1，非续行 +1）。
            assert prev is not None  # hanging 分支已保证 prev 非 None
            if prev.multi_line_cont and prev.multi_header_line:
                hdr_ln = prev.multi_header_line - 1
                prev_level = _indent_level(result[hdr_ln], indent_width)
            else:
                prev_ln = prev.line_number - 1
                prev_level = _indent_level(result[prev_ln], indent_width)
            target = prev_level + 1
        elif ctx.multi_line_cont:
            # 多行语句续行：相对语句头实际缩进 +1（同语句内续行同级，不累积）；
            # 语句头行尾 `=` 的三目链续行（multi_extra）额外 +1（ref 用 +2）
            hdr_ln = ctx.multi_header_line - 1
            hdr_level = _indent_level(result[hdr_ln], indent_width)
            target = hdr_level + 1 + (1 if ctx.multi_extra else 0)
        elif case_item_hang:
            target = ctx.scope_depth + 1
        elif ctx.block_header_of is not None:
            # 块头行：与配对 end 对齐（end 已在 pop 后处于父级深度）
            target = max(0, ctx.scope_depth - 1)
        else:
            target = ctx.scope_depth
        result[ln] = " " * (target * indent_width) + stripped
    return result


def _indent_chars(line: str) -> int:
    """行首空白字符数（tab 按 4 折；与 _indent_level 同口径的字符量化）。"""
    n = 0
    for c in line:
        if c == "\t":
            n += 4
        elif c == " ":
            n += 1
        else:
            break
    return n


def _indent_level(line: str, width: int) -> int:
    """行首缩进换算为级数（tab=4 空格）。"""
    n = 0
    for c in line:
        if c == "\t":
            n += 4
        elif c == " ":
            n += 1
        else:
            break
    return n // width
