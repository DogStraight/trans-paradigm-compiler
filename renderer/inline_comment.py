"""
inline_comment.py — tpc marker 回插（渲染后字符串级后处理）

普通注释已全部进树（注释单机制：Comment 节点 / 节点 `_comment_slots`，
渲染端结构序精确输出）——本模块只剩 **tpc marker 内部通道**：宏 marker
（行内块注释形态）与条件块占位（整行行注释形态）被 production
吞掉时经锚点收集，渲染后回插/插值定位，供 `protect_and_reverse` /
`restore_condition_blocks` 找到标记（宏/条件块还原依赖）。标记是内部编号、
非用户注释，锚点漂移风险低。**注释标点来自语言包声明**
（`lexer/comment_syntax.py`，经 `preprocessor/_markers.py`）——本模块不硬编码
`//` / `/* */`。

Doc: renderer/renderer_architecture.md（注释单机制：tpc marker 通道）
"""

import re

from lexer.comment_syntax import CommentSyntax
from preprocessor._markers import line_form_re, marker_core_re


def restore_comments(
    rendered: str,
    comment_anchors: list[dict],
    tpc_src_map: dict | None = None,
    *,
    syntax: CommentSyntax,
) -> tuple[str, int]:
    """
    通过锚点匹配将 inline comment 回注到渲染文本中。

    每个锚点条目：
        anchor: 紧前 token 内容（如 ";"、")"、"="）
        text:   注释文本（如 "// my comment"）
        line:   源行号（0-based）
        midline: 行中注释标记（P1.5——注释后还有同行代码 token）

    策略：
    1. 按源行号排序，保证插入顺序
    2. 在 [line-3, line+3] 窗口内搜索锚点
    3. 同一行连续多个匹配时取最后一个（靠近行尾）
    4. 一行仅插入一条注释
    5. 匹配失败则退化到窗口最后一行行尾追加

    ADR-0013 目标④（2026-09-05）：普通注释回插通道已删除（注释进树结构
    序渲染）——本函数**只处理 tpc marker**（行内块注释形态的宏 marker /
    整行行注释形态的条件块占位，宏/条件块还原依赖）。普通注释条目
    直接跳过。原 only_tpc / only_midline 参数删除（调用方恒 tpc 语义）。

    tpc 占位标记（midline 行注释，如表达式中间的条件块占位，
    2026-08-28 darkriscv 还原修复）：独立行插入 + 插值定位，不参与普通注释
    的锚点窗口/单行单插竞争——相邻多占位（锚相同）或渲染行号漂移时，普通
    退化会把第二个占位甩到文件尾或静默丢失（darkriscv 12 个 ifdef 缺失的
    根因）。tpc 标记按 marker 唯一性由 restore_anchors 还原，只需独立行进
    rendered（整行替换还原 ifdef 指令行）。
    """
    if not comment_anchors:
        return rendered, 0

    # 去重：parser 回溯可能导致同一条 comment 被多次收集
    # 按 (text, line) 去重，保留最先记录的锚点（最接近注释的紧前 token）
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for c in comment_anchors:
        key = (c["text"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    lines = rendered.split("\n")
    occupied: set[int] = set()
    # tpc 占位标记（midline 行注释）单独收集：最后统一独立行插入
    tpc_pending: list[tuple[int, str]] = []

    for c in sorted(unique, key=lambda x: x["line"]):
        anchor = c["anchor"]
        comment = c["text"]
        src_line = c["line"]

        if "tpc:" not in comment:
            continue  # 普通注释进树结构序渲染，不再回插（ADR-0013 目标④）
        if comment in rendered:
            # marker 已内联渲染（AST 路径）：如 ice40 端口列表内的
            # 行内块注释形态的宏 marker 既是列表结构被锚点收集、又作为块注释节点
            # 随 AST 渲染——内联位置是权威位置，锚点回插会双份（宏还原后
            # 同一段原文出现两次）。marker 编号唯一，全局判存在即可。
            continue
        if c.get("midline"):
            # tpc 占位标记（行注释）：独立行插入（见函数 docstring），
            # 不参与普通注释锚点窗口/单行单插竞争——收集到最后统一处理
            tpc_pending.append((src_line, comment))
            continue

        start = max(0, src_line - 1 - 3)
        end = min(len(lines), src_line + 3)

        best_idx = -1
        best_pos = -1

        for i in range(start, end):
            if i in occupied:
                continue
            # 从右向左搜：优先匹配行尾附近的锚点（更可能是注释位置）
            pos = lines[i].rfind(anchor)
            if pos < 0:
                continue
            # 取最后一个匹配（同一行可能有多个相同 token）
            if i > best_idx or (i == best_idx and pos > best_pos):
                best_idx = i
                best_pos = pos

        if best_idx >= 0:
            # 在锚点后插入注释
            pos = best_pos + len(anchor)
            line = lines[best_idx]
            indent = " " if pos > 0 and not line[pos - 1].isspace() else ""
            lines[best_idx] = line[:pos] + indent + "  " + comment + line[pos:]
            occupied.add(best_idx)
        else:
            # 退化到行号窗口最后一行行尾
            target = min(end - 1, len(lines) - 1)
            if target not in occupied:
                lines[target] = lines[target].rstrip() + "  " + comment
                occupied.add(target)

    # tpc 占位标记：独立行插入（插值定位尽力，退化 src_line 窗口），绝不丢失
    if tpc_pending:
        # 插值锚点（C4 收敛自 _scan_rendered_tpc；顺带修复 for 循环误缩进
        # 在 `if tpc_src_map:` 内——锚点映射为空时占位循环不执行的缺陷）
        rendered_tpc, rendered_tpc_src = _scan_rendered_tpc(lines, tpc_src_map, syntax)
        # 相邻 tpc 标记顺序插入（同 restore_line_comments）：表达式链内
        # 连续条件块（如 darkriscv IFPC 三目链的 EBREAK/INTERRUPT/DBNZ）
        # 独立插值会分散错位，相邻标记跟随上次插入位置保持结构
        last_tpc_pos: int | None = None
        last_tpc_src: int = -100
        for src_line, comment in tpc_pending:
            if last_tpc_pos is not None and src_line - last_tpc_src <= 8:
                ins = min(last_tpc_pos + 1, len(lines))
            else:
                center = _interp_tpc_line(
                    src_line, rendered_tpc_src, rendered_tpc
                )
                ins = min(center, len(lines))
            # 在插值中心附近找插入行（前插独立注释行，跳过已占用行）
            guard = 0
            while ins < len(lines) and ins in occupied and guard < len(lines):
                ins += 1
                guard += 1
            indent = ""
            if lines:
                ref = lines[min(ins, len(lines) - 1)]
                indent = " " * (len(ref) - len(ref.lstrip()))
            lines.insert(ins, indent + comment)
            # insert 后：已占用行号 >= ins 的 +1
            occupied = {o + 1 if o >= ins else o for o in occupied}
            occupied.add(ins)
            last_tpc_pos = ins
            last_tpc_src = src_line

    return "\n".join(lines), len(unique)


def _scan_rendered_tpc(
    lines: list[str], tpc_src_map: dict | None, syntax: CommentSyntax
) -> tuple[dict[str, int], dict[str, int]]:
    """扫描已渲染 tpc marker → 插值锚点（C4 位置桥收敛，2026-08-28）。

    返回 (rendered_tpc, rendered_tpc_src)：
      rendered_tpc:     marker → 渲染行号（1-based），扫**整行占位**
                        （形态由语言包声明）
      rendered_tpc_src: marker → 源行号（tpc_src_map，插值用 (源行, 渲染行) 对）
    restore_comments / restore_line_comments 两处共用，消除重复实现。
    """
    line_re = line_form_re(syntax)
    rendered_tpc: dict[str, int] = {}
    for i, l in enumerate(lines, 1):
        m = line_re.match(l)
        if m:
            rendered_tpc[m.group(1)] = i
    rendered_tpc_src: dict[str, int] = {}
    if tpc_src_map:
        rendered_tpc_src = {
            k: tpc_src_map[k] for k in rendered_tpc if k in tpc_src_map
        }
    return rendered_tpc, rendered_tpc_src


def _interp_tpc_line(src_line: int, rendered_tpc_src: dict, rendered_tpc: dict) -> int:
    """用已渲染 tpc marker（源行号 → 渲染行号）分段线性插值 src_line 的渲染位置。

    tpc marker 大多数随 AST 渲染（位置精确），少数被 production 吞掉走此回插；
    被吞 marker 的渲染位置用源行号最接近的已渲染 marker 线性插值（模块内行距
    接近线性），比裸源行号窗口（模块边界偏移 ±150）可靠。
    """
    pairs = sorted((s, rendered_tpc[m]) for m, s in rendered_tpc_src.items())
    if not pairs:
        return src_line
    prev = [p for p in pairs if p[0] <= src_line]
    nxt = [p for p in pairs if p[0] > src_line]
    if prev and nxt:
        p_src, p_r = prev[-1]
        n_src, n_r = nxt[0]
        return int(p_r + (src_line - p_src) * (n_r - p_r) / max(1, n_src - p_src))
    if prev:
        p_src, p_r = prev[-1]
        return p_r + (src_line - p_src)
    n_src, n_r = nxt[0]
    return n_r - (n_src - src_line)


def restore_line_comments(
    rendered: str,
    anchors: list[dict],
    tpc_src_map: dict | None = None,
    *,
    syntax: CommentSyntax,
) -> tuple[str, int]:
    """基于锚点的行注释回插（只处理 tpc marker，见下）。

    锚点条目：`text`（注释文本）/ `anchor`（注释后第一个有效 token）/ `line`
    （源行号）。策略：按源行号排序 → 插值定位 → 锚点窗口内落位 → `(text, line)`
    去重。四条落位路径：相邻标记顺序插入 / 锚点行首前插 / 锚点行中拆分 /
    锚点失配退化插值中心（各由 `_commit_insert` / `_commit_split` 与定位助手完成）。

    普通注释条目直接跳过（ADR-0013 目标④：注释进树结构序渲染，回插通道已删）；
    宏/条件块 marker 必须回插——否则 protect_and_reverse 找不到 marker，宏还原
    失效。宏 marker 是唯一性插值定位、不依赖锚点窗口。
    """
    if not anchors:
        return rendered, 0

    unique = _dedupe_anchors(anchors)
    lines = rendered.split("\n")
    # 已作为整行渲染存在的注释（strip 缩进比较）：随 AST 渲染（未被 production
    # skip 吞掉），不再回插——否则同一注释被"AST 渲染 + line_comment 回插"双通道
    # 重复（宏锚/条件占位 marker 在块内容易触发 parser 回溯双收集）。
    existing_lines: set[str] = {ln.strip() for ln in lines}
    inserted: set[int] = set()  # 已插入注释的行偏移，防止位置冲突
    # 相邻 tpc 标记的顺序保持（2026-08-28 darkriscv 端口列表修复）：端口组内
    # 连续条件块（`ifdef A` `ifdef B` `ifdef C` 相邻）的锚互相引用（后块锚 =
    # 前块占位文本）不可靠，独立插值定位会打乱源顺序（INTERRUPT/SIMULATION/
    # COPROCESSOR 顺序互换，sv-parser 预处理失败）。相邻标记（源行距 ≤ 8）插到
    # 上次插入位置之后，保持源顺序。
    last_tpc_pos: int | None = None
    last_tpc_src: int = -100

    # 已随 AST 渲染的 tpc: marker（位置精确）——作为被吞 marker 的插值锚点
    rendered_tpc, rendered_tpc_src = _scan_rendered_tpc(lines, tpc_src_map, syntax)

    for c in sorted(unique, key=lambda x: x["line"]):
        text = c["text"]
        anchor = c["anchor"]
        src_line = c["line"]

        if not _needs_reinsert(text, anchor, existing_lines, lines):
            continue

        if last_tpc_pos is not None and src_line - last_tpc_src <= 8:
            pos = min(last_tpc_pos + 1, len(lines))
        else:
            # 被吞 tpc marker：用已渲染 marker 分段线性插值定位
            center = _interp_tpc_line(src_line, rendered_tpc_src, rendered_tpc)
            pos = _find_anchor_line(lines, anchor, center, inserted)
            if pos >= 0 and _anchor_inside_line(lines, pos, anchor):
                _commit_split(
                    lines, inserted, rendered_tpc, rendered_tpc_src,
                    pos, text, anchor, src_line,
                )
                last_tpc_pos, last_tpc_src = pos + 1, src_line
                continue
            if pos < 0:
                # tpc 占位标记（2026-08-28 darkriscv 端口列表修复）：锚匹配
                # 失败（如锚 = 下一条注释文本，渲染后形态变化）时退化到
                # 插值中心前插独立行——restore_anchors 按 marker 整行替换
                # 还原，不静默丢失。
                pos = _free_slot(lines, inserted, center)

        _commit_insert(
            lines, inserted, rendered_tpc, rendered_tpc_src, pos, src_line, text
        )
        last_tpc_pos, last_tpc_src = pos, src_line

    return "\n".join(lines), len(unique)


def _needs_reinsert(
    text: str, anchor: str, existing_lines: set[str], lines: list[str]
) -> bool:
    """该锚点是否需要回插（四项跳过判定，任一成立即不回插）。

    跳过：非 tpc marker（普通独占行注释进树结构序渲染，ADR-0013 目标④）、
    输出里已有整行、输出里已出现行尾形态（join/attachment 输出过，避免双通道
    重复）、无锚点（无法定位）。
    """
    if "tpc:" not in text:
        return False
    if text in existing_lines:
        return False
    if any(ln.rstrip().endswith(text.strip()) for ln in lines):
        return False
    return bool(anchor)


def _anchor_inside_line(lines: list[str], pos: int, anchor: str) -> bool:
    """锚点是否落在行内容中间（非行首首个 token）——是则需拆行插入。"""
    stripped = lines[pos].lstrip()
    return stripped.find(anchor) > 0


def _commit_insert(
    lines: list[str],
    inserted: set[int],
    rendered_tpc: dict,
    rendered_tpc_src: dict,
    pos: int,
    src_line: int,
    text: str,
) -> None:
    """整行前插：按 `pos` 处缩进插入注释行，并更新已插入位置与插值锚点。"""
    _splice_line(lines, inserted, pos, _indent_at(lines, pos) + text)
    _note_tpc_anchor(rendered_tpc, rendered_tpc_src, pos, src_line, text)


def _commit_split(
    lines: list[str],
    inserted: set[int],
    rendered_tpc: dict,
    rendered_tpc_src: dict,
    best_idx: int,
    text: str,
    anchor: str,
    src_line: int,
) -> None:
    """锚点行中拆分插入（`prefix anchor suffix` → 三行）。

    行首部分 `rstrip` 收尾、注释行按原行缩进、剩余部分 `lstrip` 另起一行；
    `inserted` 里 >= best_idx 的位置整体后移 +2，并记入注释行位置
    （best_idx + 1）。
    """
    stripped = lines[best_idx].lstrip()
    content_pos = stripped.find(anchor)
    raw_pos = len(lines[best_idx]) - len(stripped) + content_pos
    before = lines[best_idx][:raw_pos]
    after = lines[best_idx][raw_pos:]
    line_indent = lines[best_idx][: len(lines[best_idx]) - len(stripped)]
    comment_line = line_indent + text
    lines[best_idx] = before.rstrip()
    lines.insert(best_idx + 1, comment_line)
    lines.insert(best_idx + 2, line_indent + after.lstrip())
    shifted = {j + 2 if j >= best_idx else j for j in inserted}
    shifted.add(best_idx + 1)
    inserted.clear()
    inserted.update(shifted)
    _note_tpc_anchor(rendered_tpc, rendered_tpc_src, best_idx + 1, src_line, text)


def _dedupe_anchors(anchors: list[dict]) -> list[dict]:
    """按 (text, line) 去重，保留首次出现（处理回溯导致的重复收集）。"""
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for c in anchors:
        key = (c["text"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _indent_at(lines: list[str], pos: int) -> str:
    """`pos` 处行的行首空白（越界取末行；空输出 → 无缩进）。"""
    if not lines:
        return ""
    ref = lines[min(pos, len(lines) - 1)]
    return " " * (len(ref) - len(ref.lstrip()))


def _find_anchor_line(
    lines: list[str], anchor: str, center: int, inserted: set[int]
) -> int:
    """插值中心 ±5 行窗口内找锚点所在行（-1 = 未命中）。

    tpc marker anchor 用**词边界匹配**：避免 'cpuregs' 误匹配
    'cpuregs_wrdata'（子串，如 TESTBUG_001 被插到 case 分支），只匹配完整
    token 出现（'cpuregs[' 等）；已插入过注释的行跳过。
    """
    start = max(0, center - 5)
    end = min(len(lines), center + 5)
    anchor_re = re.compile(rf"\b{re.escape(anchor)}\b")
    for i in range(start, end):
        if i in inserted:
            continue
        if anchor_re.search(lines[i]):
            return i
    return -1


def _free_slot(lines: list[str], inserted: set[int], center: int) -> int:
    """从插值中心起找未被占用的插入位置（顶到末尾就落到末尾）。"""
    ins = min(center, len(lines))
    guard = 0
    while ins < len(lines) and ins in inserted and guard < len(lines):
        ins += 1
        guard += 1
    return ins


def _splice_line(lines: list[str], inserted: set[int], pos: int, content: str) -> None:
    """在 `pos` 插入一行，并把 `inserted` 里 >= pos 的位置整体后移 +1 后记入 pos。"""
    lines.insert(pos, content)
    shifted = {j + 1 if j >= pos else j for j in inserted}
    shifted.add(pos)
    inserted.clear()
    inserted.update(shifted)


def _note_tpc_anchor(
    rendered_tpc: dict, rendered_tpc_src: dict, pos: int, src_line: int, text: str
) -> None:
    """tpc 标记插入后更新插值锚点（2026-08-28 darkriscv 块尾占位修复）：

    先插入的 marker 成为后续 marker 的插值锚点——块头占位插入后，块尾占位
    （源行距超过相邻阈值）的插值不再依赖旧锚点，位置更准（否则 `endif`
    占位错位导致条件块嵌套深度错乱）。
    """
    m = marker_core_re().search(text)
    if m:
        rendered_tpc[m.group(1)] = pos + 1  # 1-based 渲染行
        rendered_tpc_src[m.group(1)] = src_line

