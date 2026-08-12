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
    # 条件编译指令行（`ifdef/`ifndef/`else/`elsif/`endif）：PicoRV32 风格顶格，
    # 不随代码块缩进（gen 原始即顶格，indent 按 depth 重算会破坏）
    _IFDEF_DIRECTIVE = ("`ifdef", "`ifndef", "`else", "`elsif", "`endif")
    for ctx in contexts:
        # 用 line_number 定位行（1-based），防御 contexts 与行索引错位
        ln = ctx.line_number - 1
        if ln < 0 or ln >= len(result):
            continue
        stripped = result[ln].lstrip()
        if not stripped:
            continue  # 空行 / 纯空白保持
        if stripped.startswith(_IFDEF_DIRECTIVE):
            result[ln] = stripped
            continue
        if ctx.block_header_of is not None:
            # 块头行：与配对 end 对齐（end 已在 pop 后处于父级深度）
            target = max(0, ctx.scope_depth - 1)
        else:
            target = ctx.scope_depth
        result[ln] = " " * (target * indent_width) + stripped
    return result
