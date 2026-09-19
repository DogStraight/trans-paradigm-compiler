"""inst_port.py — 模块实例化端口连接对齐 pass

结构：
    .port_name ( connection ),
    ────────── ─ ────────── ─ ─
      name       lp   expr   rp term

能力：
  1. 拆单行多端口（`.clk(clk), .resetn(resetn), ...` → 每行一个），括号平衡
  2. 连续端口行分组对齐 name / expr 两列（与 ref 格式一致）

依赖 boundary.py 提供的 RichLineContext 元数据；拆分后**就地同步 contexts**
（每段派生复制源行 ctx）——根治"拆行后 contexts 与 lines 错位"的行号漂移
（ADR-0006 阶段 3：带结构行，后续 wrap 按 index 取 contexts 不再拿错行）。

AST 辅助（2026-08-28）：parser 注入时对齐用实例块解析的端口 span——
跨行端口（concat 多行展开 `.RADDR({pd(RADDR_10),` + 续行）的表达式范围
由 AST 确定，不靠单行括号平衡推断。修复：未闭合行被 _port_parse 误判为
"行尾即表达式结束"而伪补 `)`（ice40 `.RADDR({pd(RADDR_10),` →
`.RADDR({pd(RADDR_10),      )`）。无 parser 时未闭合行保守跳过对齐。
"""

from __future__ import annotations

import re
from typing import Any

from ..boundary import LineContext

# 端口名：`.` + 标识符 + 可选 `(` 前空格（end 指向 `(`）
_PORT_NAME_RE = re.compile(r"\.(\w[\w\[\]]*)\s*\(")

# _port_parse 未闭合哨兵：行内 `(` 深度未归零（跨行端口首行）
_UNCLOSED = object()


def _port_parse(stripped: str, m) -> tuple[int, int, int, str] | None | object:
    """解析 `.name(` 端口段。括号平衡找匹配 `)`。

    Returns: (end, expr_start, expr_end, term)
        end       含尾随 `,`/`;` 的段结束位置（供拆分）
        expr_start/expr_end  expr 区间（exclusive，不含 `)`）
        term      尾随 `,` 或 `;`（可为空）
    非纯端口（`)` 后还有内容，如参数化实例化的 `) inst_name (`）返回 None。
    行内 `(` 深度未归零（跨行端口首行）返回 _UNCLOSED 哨兵。
    """
    i = m.end() - 1  # '('
    depth = 0
    expr_start = m.end()
    while i < len(stripped):
        if stripped[i] == "(":
            depth += 1
        elif stripped[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0:
        return _UNCLOSED  # 行内未闭合：跨行端口首行，不推断表达式范围
    expr_end = i  # 匹配 `)` 的位置（exclusive）
    end = i + 1
    term = ""
    if end < len(stripped) and stripped[end] in (",", ";"):
        term = stripped[end]
        end += 1
    elif end < len(stripped) and stripped[end:].strip():
        return None  # 后接其他内容 → 非纯端口段
    return (end, expr_start, expr_end, term)


def _split_line_ports(line: str) -> list[str] | None:
    """行内含多个 `.name(` → 拆成每行一个端口（括号平衡）。

    Returns: 新行列表（每行一个端口段），无多端口或含非纯端口段/未闭合段
    返回 None。
    """
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]
    ms = list(_PORT_NAME_RE.finditer(stripped))
    if len(ms) <= 1:
        return None
    segs = []
    for m in ms:
        parsed = _port_parse(stripped, m)
        if parsed is None or parsed is _UNCLOSED:
            return None  # 含参数化实例化/跨行端口等非纯端口行 → 整行不拆（保安全）
        assert isinstance(parsed, tuple)
        end, _, _, _ = parsed
        segs.append(indent + stripped[m.start():end].rstrip())
    return segs


def _match_port(line: str):
    """解析单端口行 `.name(expr),`（括号平衡，支持嵌套）。

    Returns: (indent, name, expr, term) 或 None（非纯端口行/未闭合行）。
    """
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]
    m = _PORT_NAME_RE.match(stripped)
    if not m:
        return None
    parsed = _port_parse(stripped, m)
    if parsed is None or parsed is _UNCLOSED:
        return None
    assert isinstance(parsed, tuple)
    _, expr_start, expr_end, term = parsed
    expr = stripped[expr_start:expr_end].strip()
    return (indent, "." + m.group(1), expr, term)


def _is_port_line(line: str) -> bool:
    stripped = line.lstrip()
    m = _PORT_NAME_RE.match(stripped)
    if not m:
        return False
    parsed = _port_parse(stripped, m)
    return parsed is not None and parsed is not _UNCLOSED


def _is_unclosed_port_line(line: str) -> bool:
    """跨行端口首行：`.name(` 形态但行内括号未闭合。"""
    stripped = line.lstrip()
    m = _PORT_NAME_RE.match(stripped)
    if not m:
        return False
    return _port_parse(stripped, m) is _UNCLOSED


def _align_group(lines: list[str], group: list[int]) -> None:
    """对齐一组端口行的 name / expr 两列（ref 格式：`.name(...expr...),`）。

    缩进统一为组内最大缩进：原始渲染常让首端口行（实例声明行的续行）
    比后续端口行多一层缩进（如 `.clk` 12 / `.resetn` 8），ref 统一对齐。
    """
    rows = []
    for idx in group:
        m = _match_port(lines[idx])
        if m:
            rows.append((idx, m))
    if len(rows) < 2:
        return
    max_name = max(len(r[1][1]) for r in rows)
    max_expr = max(len(r[1][2]) for r in rows)
    max_indent = max(len(r[1][0]) for r in rows)
    for idx, (_, name, expr, term) in rows:
        lines[idx] = " " * max_indent + name.ljust(max_name) + "(" + expr.ljust(max_expr) + ")" + term


def _is_comment_line(line: str) -> bool:
    """注释行（`//` 或 `/*` 起头，行内无端口）——对齐分组的透明行。"""
    stripped = line.lstrip()
    return stripped.startswith("//") or stripped.startswith("/*")


def _align_contiguous_ports(lines: list[str]) -> None:
    """连续端口行分组对齐（组间按非端口行分隔）。

    注释行（`//State` 等端口组间注释）视为透明：不打断端口连续组——
    注释是端口组的语义分隔（分组注释），renderer 对它的槽位渲染（前端口
    trailing / 后端口 leading）每轮可能漂移；若把注释行当组边界，分组
    边界随注释位置变化 → 对齐列宽每轮不同 → 非幂等振荡。透明处理后
    无论注释渲染在组内何处，端口行始终同组同列宽，对齐稳定。
    """
    i = 0
    n = len(lines)
    while i < n:
        if _is_port_line(lines[i]):
            group = [i]
            j = i + 1
            while j < n:
                if _is_port_line(lines[j]):
                    group.append(j)
                    j += 1
                elif _is_comment_line(lines[j]):
                    # 注释行透明：跳过，不打断组（也不入组参与对齐）
                    j += 1
                else:
                    break
            if len(group) >= 2:
                _align_group(lines, group)
            i = j
        else:
            i += 1


def _emit_line_with_ctx(
    result: list[str],
    new_ctxs: list[LineContext],
    line: str,
    ctx: LineContext | None,
    segs: list[str] | None,
) -> None:
    """一行（或拆出的多段）与 contexts 同步追加：拆段复制同一源行 ctx。"""
    if segs is None:
        result.append(line)
        if ctx is not None:
            new_ctxs.append(ctx)
        return
    result.extend(segs)
    if ctx is not None:
        new_ctxs.extend([ctx] * len(segs))


def run_inst_port_align(lines: list[str], contexts: list[LineContext], parser: Any = None) -> list[str]:
    """拆单行多端口 + 连续端口行对齐。

    拆行时同步 contexts：每段派生复制源行 ctx（line_number 保持源行号，
    scope/ifdef 元数据不变），contexts 与 lines 始终同长——根治拆行后
    行号漂移（后续 wrap 按 index 取 contexts 不再错位）。

    parser：可选，语法感知（AST 辅助）——跨行端口（concat 多行展开等）
    的表达式范围由实例块解析的端口 span 确定，跨行端口参与 name 列对齐、
    expr 保留原文。未传入则跨行端口首行保守跳过（不参与对齐）。
    """
    result: list[str] = []
    new_ctxs: list[LineContext] = []
    for i, line in enumerate(lines):
        ctx = contexts[i] if i < len(contexts) else None
        # impl 绑定语句（`impl type.role (ports)`）：`type.role` 会被当端口段拆开
        # （如 `impl spi.master (.clk(clk),` 拆成 `.master(.clk(clk),)` + `.clk(clk),`），
        # 整行跳过拆分——其后续 `.port(expr)` 行仍走连续端口对齐。
        segs = None if line.lstrip().startswith("impl ") else _split_line_ports(line)
        _emit_line_with_ctx(result, new_ctxs, line, ctx, segs)
    # 就地同步 contexts（调用方持有同一列表；wrap 后续按 index 取）
    if new_ctxs:
        contexts[:] = new_ctxs
    if parser is not None:
        _align_with_ast(result, parser)
    else:
        _align_contiguous_ports(result)
    return result


# ── AST 辅助（parser 注入）────────────────────────────────


def _iter_port_groups_ast(lines: list[str]):
    """扫描端口组（AST 路径）：`.name(` 起始的连续行，跨行端口首行也入组，
    其续行（未闭合端口 expr 的后续片段，可多行）透明跳过。
    yield (start, end) [start, end) 端口行索引区间（end 为组后第一行）。"""
    i = 0
    n = len(lines)
    while i < n:
        if _is_port_line(lines[i]) or _is_unclosed_port_line(lines[i]):
            start = i
            in_unclosed = _is_unclosed_port_line(lines[i])
            j = i + 1
            while j < n:
                if _is_port_line(lines[j]):
                    in_unclosed = False
                    j += 1
                elif _is_unclosed_port_line(lines[j]):
                    in_unclosed = True
                    j += 1
                elif _is_comment_line(lines[j]):
                    j += 1  # 注释行透明（与文本路径同语义）
                elif (
                    in_unclosed
                    and lines[j].strip()
                    and not lines[j].lstrip().startswith((".", "`"))
                ):
                    # 未闭合端口续行（expr 后续片段，可多行链），组内透明
                    j += 1
                else:
                    break
            yield start, j
            i = j
        else:
            i += 1


def _find_instance_head(lines: list[str], g_start: int) -> int | None:
    """向上找实例头行：组前最近的非空非注释行，行尾 `(` 且非 `.name(` 形态。

    中途碰到普通行（非注释/非空）→ 组前不是实例头，返回 None。
    """
    i = g_start - 1
    while i >= 0:
        s = lines[i].rstrip()
        if s.endswith("(") and not _PORT_NAME_RE.search(s):
            return i
        if s.strip() and not _is_comment_line(s):
            return None
        i -= 1
    return None


def _find_instance_tail(lines: list[str], head: int) -> int | None:
    """从实例头行起累计 `(`/`)` 深度 → 深度归零且行尾 `);` 的尾行索引。

    端口表达式的嵌套括号已含在内；跨行 concat 端口的 `)` 只使深度下降不
    归零，不会误判为尾。括号提前失衡（深度 <0）→ None（块不完整）。
    """
    depth = 0
    j = head
    while j < len(lines):
        s = lines[j]
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if depth == 0 and s.rstrip().endswith(");"):
            return j
        if depth < 0:
            return None  # 括号提前失衡 → 块不完整
        j += 1
    return None


def _find_instance_block(lines: list[str], g_start: int, g_end: int):
    """从端口组向上找实例头行（行尾 `(` 且非 `.name(` 形态），向下按括号
    深度找 `);` 尾行（跨行端口表达式内的 `)` 不误判为实例尾）。

    Returns: (head_idx, tail_idx) 或 None（找不到完整块）。
    """
    del g_end  # 尾行由括号深度扫描定位，g_end 仅作签名兼容（组区间上界）
    head = _find_instance_head(lines, g_start)
    if head is None:
        return None
    tail = _find_instance_tail(lines, head)
    if tail is None:
        return None
    return head, tail


def _max_pos_line(node: Any) -> int:
    """node 子树内最大 _pos_line（0 = 无定位信息）。"""
    best = getattr(node, "_pos_line", 0) or 0
    iter_children = getattr(node, "iter_children", None)
    if iter_children is None:
        return best  # 非 Node 对象（无 iter_children）→ 自身行号即结果
    for child in iter_children():
        best = max(best, _max_pos_line(child))
    return best


def _collect_named_port_spans(n: Any, spans: list) -> bool:
    """DFS 找 ModuleInst 并收集其 NamedPortConnect 的 (起始行, 结束行)。

    Returns: 是否已命中 ModuleInst（命中即停止下钻）。
    """
    if getattr(n, "node_name", None) == "ModuleInst":
        ports = getattr(n, "ports", None)
        items = getattr(ports, "items", None) if ports is not None else None
        if isinstance(items, list):
            for p in items:
                if getattr(p, "node_name", None) == "NamedPortConnect":
                    s = getattr(p, "_pos_line", 0) or 0
                    e = _max_pos_line(getattr(p, "value", None))
                    spans.append((s, e))
        return True
    iter_children = getattr(n, "iter_children", None)
    if iter_children is None:
        return False
    return any(_collect_named_port_spans(child, spans) for child in iter_children())


def _parse_block_ast(parser: Any, wrapped: str):
    """包装源码 → AST；解析失败/截断/无 lexer → None（调用方回退文本启发式）。"""
    import contextlib
    import io as _io

    lexer = getattr(parser, "lexer", None)
    if lexer is None:
        return None
    try:
        tokens = lexer.tokenize(wrapped)
        with contextlib.redirect_stderr(_io.StringIO()):
            ast = parser.parse(tokens)
    except Exception:  # noqa: BLE001 — 解析失败是预期结果（实例块可能不是合法独立模块）
        # → 返回 None，调用方回退文本括号启发式；此处不承诺具体异常类型
        # （lexer/parser 各自抛什么属实现细节），故保留宽捕获。
        return None
    if ast is None or getattr(parser, "_parse_truncated", False):
        return None
    return ast


def _parse_instance_ports(
    parser: Any, block_lines: list[str]
):
    """包装解析实例块，返回每个 NamedPortConnect 的 span。

    block_lines[0] 即实例头行（`mod inst (`）。包装：
    `module _tpc_p;\n<block_lines>\nendmodule`。
    Returns: list[(start_off, end_off)]（相对 block_lines 的行偏移，
    head 为偏移 0），解析失败返回 None。
    """
    wrapped = (
        "module _tpc_p;\n"
        + "\n".join(block_lines)
        + "\nendmodule\n"
    )
    ast = _parse_block_ast(parser, wrapped)
    if ast is None:
        return None
    # 找 ModuleInst（包装后 head_line 在 L2），行号映射：wrapped 的
    # L1 = `module _tpc_p;`，L2 = head_line，L(2+k) = block_lines[k]
    # → span 行号 → block 偏移 = line - 2
    spans: list[tuple[int, int]] = []
    _collect_named_port_spans(ast, spans)
    return [(max(0, s - 2), max(0, e - 2)) for s, e in spans]


def _align_group_ast(lines: list[str], group: list[int], spans: dict[int, tuple[int, int]]) -> None:
    """AST 辅助对齐：跨行端口参与 name 列对齐、expr 保留原文；单行端口全对齐。"""
    rows = []
    for idx in group:
        m = _match_port(lines[idx])
        if m:
            rows.append((idx, m, False))
        elif _is_unclosed_port_line(lines[idx]):
            stripped = lines[idx].lstrip()
            indent = lines[idx][: len(lines[idx]) - len(stripped)]
            m2 = _PORT_NAME_RE.match(stripped)
            if m2:
                # expr 原文 = `(` 之后到行尾（不含行尾空白）
                expr_raw = stripped[m2.end():].rstrip()
                rows.append((idx, (indent, "." + m2.group(1), expr_raw, ""), True))
    if len(rows) < 2:
        return
    max_name = max(len(r[1][1]) for r in rows)
    max_expr = max(len(r[1][2]) for r in rows)
    max_indent = max(len(r[1][0]) for r in rows)
    for idx, (_, name, expr, term), unclosed in rows:
        if unclosed:
            # 跨行端口：name 列对齐，expr 原样（续行不变）
            stripped = lines[idx].lstrip()
            m = _PORT_NAME_RE.match(stripped)
            assert m is not None
            expr_raw = stripped[m.end():].rstrip()
            lines[idx] = (
                " " * max_indent
                + name.ljust(max_name)
                + "("
                + expr_raw
            )
        else:
            lines[idx] = (
                " " * max_indent
                + name.ljust(max_name)
                + "("
                + expr.ljust(max_expr)
                + ")"
                + term
            )
    del spans  # 对齐用行级判定即可；spans 保留给未来 expr 列宽精确化


def _align_with_ast(lines: list[str], parser: Any) -> None:
    """AST 辅助对齐主流程：对每个端口组定位实例块、解析拿 span，成功则
    用 AST 判定跨行端口（参与 name 列对齐）；失败回退文本路径（保守）。"""
    for g_start, g_end in _iter_port_groups_ast(lines):
        group = list(range(g_start, g_end))
        block = _find_instance_block(lines, g_start, g_end)
        if block is None:
            # 无实例头/尾 → 文本路径（未闭合行已被 _match_port 排除）
            _align_group(lines, [i for i in group if _is_port_line(lines[i])])
            continue
        head_idx, tail_idx = block
        block_lines = lines[head_idx : tail_idx + 1]
        spans = _parse_instance_ports(parser, block_lines)
        if spans is None:
            # 解析失败（宏调用/非纯结构）→ 文本路径
            _align_group(lines, [i for i in group if _is_port_line(lines[i])])
            continue
        # span 偏移映射回全局行号：head_idx 为偏移 0
        span_of: dict[int, tuple[int, int]] = {}
        for s, e in spans:
            span_of[head_idx + s] = (head_idx + s, head_idx + e)
        _align_group_ast(lines, group, span_of)
