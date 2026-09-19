"""
列对齐 — 按语义列对齐。

从右向左推断各语义列位置。结构参考 grammar 中 Declarator / TypeSpec 定义：
  indent | first_token | opt_type | opt_range | name | opt_array_range | opt_init

终结符（, ;）保留在 name 或 array_range/init 中，不对齐。

依赖 boundary.py 提供的 RichLineContext 元数据 + grouping.py 分组工具。
"""

from __future__ import annotations

import re
from typing import Any

from ..boundary import LineContext
from ..grouping import group_by_scope, compute_column_widths


# 纯数字位宽 `[msb:lsb]`（高位数字右对齐用；含表达式/参数如 `[WIDTH-1:0]` 不匹配）
_RANGE_RE = re.compile(r"^\[(\d+):(\d+)\]$")


def _align_range_internal(rows: list[list[str]], col: int = 3) -> None:
    """组内位宽列内部右对齐（ref 风格：`[3:0]` 与 `[31:0]` 同组时 → `[ 3:0]`）。

    只补 msb 前空格，不改 token 内容；msb 全为单数字时不改动。
    """
    msb_width = 0
    for row in rows:
        r = row[col] if len(row) > col else ""
        m = _RANGE_RE.match(r)
        if m:
            msb_width = max(msb_width, len(m.group(1)))
    if msb_width <= 1:
        return
    for row in rows:
        if len(row) <= col:
            continue
        m = _RANGE_RE.match(row[col])
        if m:
            row[col] = "[%*s:%s]" % (msb_width, m.group(1), m.group(2))


def _build_matcher(cfg: dict) -> Any | None:
    if "first_token" in cfg:
        tokens = cfg["first_token"]
        if isinstance(tokens, str):
            tokens = [tokens]
        token_set = frozenset(tokens)
        return lambda line: _first_token(line) in token_set if _first_token(line) else False
    if "regex" in cfg:
        import re
        pattern = re.compile(cfg["regex"])
        return lambda line: bool(pattern.match(line.lstrip()))
    return None


def _first_token(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped:
        return None
    return stripped.split()[0]


class _TokenScan:
    """列对齐 tokenizer 的扫描状态：输出缓冲即状态（故用类而非闭包）。

    切分规则的总纲：括号内（`[...]`）不切空白/结构符（位宽/索引表达式是
    一个整体）；字符串与注释各按自有规则**整段**成一个 token——各分支的
    具体理由随方法走（都是真实语料踩出来的）。
    """

    __slots__ = ("tokens", "buf", "in_bracket", "in_string")

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.buf: list[str] = []
        self.in_bracket = 0
        self.in_string = False

    def flush(self) -> None:
        """把缓冲并成一个 token（缓冲空则无操作）。"""
        if self.buf:
            self.tokens.append("".join(self.buf))
            self.buf = []

    def feed(self, text: str, i: int) -> int:
        """吃掉 text[i]（含可能的整段消费），返回下一个游标位置。"""
        ch = text[i]
        if self.in_string:
            return self._feed_string(text, i)
        if ch == '"':
            self.in_string = True
            self.buf.append(ch)
            return i + 1
        if ch == "/":
            j = self._feed_comment(text, i)
            if j is not None:
                return j
        return self._feed_content(text, i)

    def _feed_string(self, text: str, i: int) -> int:
        """字符串态：转义对整体入缓冲；闭合引号结束字符串态。"""
        ch = text[i]
        self.buf.append(ch)
        if ch == "\\" and i + 1 < len(text):
            self.buf.append(text[i + 1])
            return i + 2
        if ch == '"':
            self.in_string = False
        return i + 1

    def _feed_comment(self, text: str, i: int) -> int | None:
        """`//` 行注释 / `/*` 块注释整段成 token；不是注释起始 → None。"""
        if text.startswith("//", i):
            return self._feed_line_comment(text, i)
        if text.startswith("/*", i):
            return self._feed_block_comment(text, i)
        return None

    def _feed_line_comment(self, text: str, i: int) -> int:
        """行注释整段成单个 token（吃到最后）。

        旧实现按空白把注释词切开：`_parse_decl_parts` 会拿注释里最后一个
        标识符当 name，重组出 `reg  IFPC // 32-bit program counter IF
        [31:0] state`（`;` 丢在注释里）——声明行语法被破坏（2026-09-17）。
        """
        self.flush()
        self.tokens.append(text[i:])
        return len(text)

    def _feed_block_comment(self, text: str, i: int) -> int:
        """块注释整段成单个 token（到本行内 `*/` 为止）；未闭合则到行尾。"""
        self.flush()
        end = text.find("*/", i + 2)
        end = len(text) if end < 0 else end + 2
        self.tokens.append(text[i:end])
        return end

    def _feed_equals(self, text: str, i: int) -> int:
        """连续等号（`==`/`===`）成单个运算符 token，不拆成多个 `=`。

        防 `a == b` 被拆成 `a = = b`（重组后破坏运算符语义）；`!=`/`!==`
        同理——前导 `!` 已进缓冲，弹出并入等号 token（防 `d !== e` 被拆成
        `d ! == e`，2026-08-28 真实语料审查发现）。
        """
        end = i
        n = len(text)
        while end < n and text[end] == "=":
            end += 1
        eq = text[i:end]
        if self.buf and self.buf[-1] == "!":
            self.buf.pop()
            eq = "!" + eq
        self.flush()
        self.tokens.append(eq)
        return end

    def _feed_content(self, text: str, i: int) -> int:
        """普通字符：括号深度记账 + 结构符/空白切分（括号内全入缓冲）。"""
        ch = text[i]
        if ch == "[":
            self.in_bracket += 1
        elif ch == "]":
            self.in_bracket -= 1
        elif self.in_bracket > 0:
            pass  # 括号内不切分——位宽/索引表达式是一个整体
        elif ch == "=":
            return self._feed_equals(text, i)
        elif ch in "(),;={}":
            # 结构符独立成 token（即使粘连，如 `ffff_ffff,` / `(expr` / `0}`）
            self.flush()
            self.tokens.append(ch)
            return i + 1
        elif ch.isspace():
            self.flush()
            return i + 1
        self.buf.append(ch)
        return i + 1


def _tokenize_bracket_aware(line: str) -> list[str]:
    """行 → token 列表（首元素是缩进）；切分规则见 `_TokenScan`。"""
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    if not stripped:
        return []
    scan = _TokenScan()
    i = 0
    while i < len(stripped):
        i = scan.feed(stripped, i)
    scan.flush()
    return [indent] + scan.tokens


def _is_ident(tok: str) -> bool:
    """标识符：字母/下划线开头。数字字面量（32'h、'h、0x1F 等）不算。"""
    if not tok:
        return False
    return tok[0].isalpha() or tok[0] == "_"


def _is_comment_token(tok: str) -> bool:
    """注释 token（`//` 行注释 / `/*` 块注释整段，见 _tokenize_bracket_aware）。"""
    return tok.startswith("//") or tok.startswith("/*")


def _is_multidecl(rest: list[str]) -> bool:
    """检测一行多声明/多端口（括号外逗号分隔多个标识符，如 `reg a, b;`、
    `input clk, resetn,`）。行尾终结符逗号（`param = 1,`）不算。

    单组提取（`_extract_semantic`）据此跳过（防丢名字）；多声明行的
    逐单元对齐走 `_extract_semantic_multi`。
    """
    depth = 0
    for k, t in enumerate(rest):
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        elif t == "," and depth == 0:
            # 逗号后还有非终结符内容 → 多声明
            for nxt in rest[k + 1:]:
                if nxt in (",", ";"):
                    continue
                return True
    return False


def _find_top_level_assign(rest: list[str]) -> int:
    """声明侧顶层 `=` 的下标（圆括号/拼接内忽略）；无 → -1。"""
    depth = 0
    for k, t in enumerate(rest):
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        elif t == "=" and depth == 0:
            return k
    return -1


def _has_expr_separators(decl: list[str]) -> bool:
    """声明侧是否含拼接/复制（`{}`）或圆括号——两者都让列语义不可靠。

    - 拼接/复制（`assign {a, b} = ...`）：其逗号是表达式分隔符，不是多声明
      分隔——走列路径会把逗号当列分隔吞掉（曾毁掉 concat LHS 的
      `{a, b}` → `{a  b}`，fidelity 0.95→0.33）。
    - 圆括号（net 声明的 drive/charge strength `(strong1, pull0)` /
      `(small)`，nettypes 插件 A.2.2.2）：括号内是强度语义不是列语义，走列
      路径会把 `(strong1, pull0)` 拆坏（逗号粘连 token + name 误判）。
    """
    for t in decl:
        if t in ("{", "}", "(", ")"):
            return True
    return False


def _last_ident_index(items: list[str]) -> int:
    """从右往左找最后一个标识符的下标；没有 → -1。"""
    i = len(items) - 1
    while i >= 0 and not _is_ident(items[i]):
        i -= 1
    return i


def _split_type_and_range(head: list[str]) -> tuple[str, str]:
    """name 左侧 token → (opt_type 文本, opt_range)。

    range 认 `[` 开头的 token（`[7:0]` 是一个整体 token）；其余修饰 token
    （如 `localparam integer`）按原序拼进 opt_type。
    """
    opt_type = ""
    opt_range = ""
    for t in head:
        if t.startswith("["):
            opt_range = t
        else:
            opt_type = (opt_type + " " + t).strip() if opt_type else t
    return opt_type, opt_range


def _parse_decl_parts(rest: list[str]) -> tuple[str, str, str, str] | None:
    """解析声明侧（不含 first token）：返回 (opt_type, opt_range, name, init)。

    以顶层 `=` 定位 init（`=` 后整体保留），避免 `32'h ffff_ffff` 中
    `ffff_ffff` 被误判为 name 而丢真名（曾丢 LATCHED_IRQ/STACKADDR）。
    声明侧含拼接/复制表达式或圆括号时无法可靠解析 → None（理由见
    `_has_expr_separators`）。
    """
    eq_idx = _find_top_level_assign(rest)
    if eq_idx >= 0:
        decl = rest[:eq_idx]
        # init 保留 `=`（防 _join_semantic 重组丢等号）
        init = "= " + " ".join(rest[eq_idx + 1:]).strip()
    else:
        decl = rest
        init = ""

    if _has_expr_separators(decl):
        return None

    d = [t for t in decl if t not in (",", ";")]
    # name = 最后一个标识符（从右往左）
    i = _last_ident_index(d)
    if i < 0:
        return None
    name = d[i]
    # name 右侧杂项（端口列表关闭 `)` 等）保留，并入 init 尾部（防丢）
    trailing = " ".join(d[i + 1:]).strip()
    if trailing:
        init = (init + " " + trailing).strip() if init else trailing
    opt_type, opt_range = _split_type_and_range(d[:i])
    return opt_type, opt_range, name, init


def _extract_semantic(tokens: list[str]) -> list[str] | None:
    """从 token 列表提取语义列（单声明）。

    Returns: [indent, first, opt_type, opt_range, name, opt_array_range, opt_init]
    无法可靠解析（一行多声明等）返回 None（调用方跳过，保留原文）。

    多声明的逐单元对齐走 _extract_semantic_multi（P1.5：多声明品类对齐）。
    """
    if len(tokens) < 2:
        return None
    indent = tokens[0]
    first = tokens[1]
    rest = list(tokens[2:])

    # 注释行跳过（防 `// comment` 被当声明）；含注释 token 的行同样跳过——
    # 尾注（`reg x;  // c`）不是声明单元，参与列解析会把注释词当标识符/丢 `;`
    # （与 _extract_semantic_multi 的尾注保护同约定：保留原文不重排，2026-09-17）。
    if first.startswith("//") or any(_is_comment_token(t) for t in rest):
        return None

    # 结尾终结符（,;）独立保存，_join_semantic 重组时加回（防丢）
    term = ""
    while rest and rest[-1] in (",", ";"):
        term = rest.pop() + term

    if _is_multidecl(rest):
        return None

    parts = _parse_decl_parts(rest)
    if parts is None:
        return None
    opt_type, opt_range, name, init = parts
    return [indent, first, opt_type, opt_range, name, "", init, term]


def _split_multi_units(rest: list[str]) -> list[list[str]]:
    """顶层逗号切分声明单元（圆括号/位拼接内忽略——`(` 内逗号是表达式分隔）。"""
    units: list[list[str]] = []
    depth = 0
    cur: list[str] = []
    for t in rest:
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        if t == "," and depth == 0:
            units.append(cur)
            cur = []
        else:
            cur.append(t)
    units.append(cur)
    return units


def _has_comment_token(units: list[list[str]]) -> bool:
    """任一单元含注释 token → 整行跳过。

    尾注注释保护：`input clk, // 行内注释` / `reg a, /* c */ b;` 的注释不是
    声明单元（保留原文，与旧 `_is_multidecl` 跳过行为一致）；纯声明多声明行
    （无注释）才参与逐单元对齐。
    """
    for u in units:
        for t in u:
            if _is_comment_token(t):
                return True
    return False


def _unit_cols(
    unit: list[str], first: str, ui: int, n: int, indent: str, term: str
) -> list[str] | None:
    """单声明单元 → 8 列语义行；解析失败 → None。

    类型头（first/opt_type）只挂首单元；单元间 term 为逗号、行尾终结符归末
    单元；非首单元 indent 置空（重组时不重复缩进）。空单元（连续逗号）→
    None（保守跳过整行）。
    """
    if not unit:
        return None
    parts = _parse_decl_parts(unit)
    if parts is None:
        return None
    opt_type, opt_range, name, init = parts
    return [
        indent if ui == 0 else "",
        first if ui == 0 else "",
        opt_type if ui == 0 else "",
        opt_range,
        name,
        "",
        init,
        "," if ui < n - 1 else term,
    ]


def _extract_semantic_multi(tokens: list[str]) -> list[list[str]] | None:
    """提取一行的全部语义单元（P1.5 多声明品类对齐）。

    单声明 → [单组]（等价 _extract_semantic）；多声明 → 每声明一组。

    重组形态（run_category_pass）：首单元参与列对齐（与单声明同）；后续
    单元按 `, ` 单分隔紧跟（不参与填充）——ref 基准风格 `reg dout,
    din_0, din_1;`，与 Verible 单行多声明形态一致。
    """
    if len(tokens) < 2:
        return None
    indent = tokens[0]
    first = tokens[1]
    rest = list(tokens[2:])

    if first.startswith("//"):
        return None

    if not _is_multidecl(rest):
        single = _extract_semantic(tokens)
        return [single] if single is not None else None

    term = ""
    while rest and rest[-1] in (",", ";"):
        term = rest.pop() + term

    units = _split_multi_units(rest)
    if _has_comment_token(units):
        return None

    out: list[list[str]] = []
    n = len(units)
    for ui, unit in enumerate(units):
        cols = _unit_cols(unit, first, ui, n, indent, term)
        if cols is None:
            return None
        out.append(cols)
    return out


def _join_column(j: int, val: str, widths: list[int], pad_columns: bool) -> str:
    """单列的重组文本。

    前 3 列（first/opt_type/opt_range）对齐：空列补到列宽 + 分隔。第 4 列
    （name）从"内容起点"（前 3 列后）开始但不填充自身，终结符（`,`/`;`）紧跟
    name（ref 端口/声明的 name 起始列对齐风格）；其余列前加单个空格分隔。
    """
    if j <= 3:
        if not pad_columns:
            # 多声明行的后续声明单元：跳过列宽填充——前缀空列不再补
            # `width+1` 空格（旧实现致名字列随上一单元长度漂移，226 处实测）；
            # 非空列防御性保留（正常提取下恒空）。
            return val + " " if val else ""
        w = widths[j] if j < len(widths) else 0
        return val + " " * (w - len(val) + 1) if val else " " * (w + 1)
    if j == 4:
        return val
    return " " + val if val else ""


def _join_semantic(cols: list[str], widths: list[int], pad_columns: bool = True) -> str:
    # 第 8 列为结尾终结符（,;），不参与对齐，直接追加
    term = cols[7] if len(cols) >= 8 else ""
    body = cols[1:7] if len(cols) >= 8 else cols[1:]
    parts = [cols[0]]
    for j, val in enumerate(body, start=1):
        parts.append(_join_column(j, val, widths, pad_columns))
    if term:
        parts.append(term)
    return "".join(parts)


def run_category_pass(
    lines: list[str],
    contexts: list[LineContext],
    cfg: dict,
) -> list[str]:
    match_fn = _build_matcher(cfg.get("matcher", {}))
    if match_fn is None:
        return list(lines)
    break_distance = cfg.get("break_distance", 3)
    result = list(lines)

    groups = group_by_scope(lines, contexts, match_fn, break_distance)
    for group in groups:
        # 多单元提取（P1.5 多声明品类对齐）：多声明行拆多单元，全部单元
        # 参与列宽计算（首单元的类型头列宽；后续空列随全组最宽值）；
        # 重组时首单元参与对齐，后续单元 `, ` 单分隔（见下）。
        row_groups: list[list[list[str]]] = []
        valid: list[int] = []
        for idx in group:
            units = _extract_semantic_multi(
                _tokenize_bracket_aware(result[idx])
            )
            if units:
                row_groups.append(units)
                valid.append(idx)
        if len(valid) < 2:
            continue
        rows = [cols for units in row_groups for cols in units]
        # 位宽列内部右对齐（`[3:0]` → `[ 3:0]`），与 ref 同组内对齐一致
        _align_range_internal(rows)
        widths = compute_column_widths(rows, 5)
        for gi, idx in enumerate(valid):
            units = row_groups[gi]
            # 重组：首单元带 indent/类型头、参与列对齐；后续声明单元以
            # `, ` 单分隔紧跟（pad_columns=False——不参与填充，名字列不再
            # 随上一单元长度漂移；ref 基准风格 / Verible 单行多声明形态）。
            joined = _join_semantic(units[0], widths) + "".join(
                " " + _join_semantic(c, widths, pad_columns=False)
                for c in units[1:]
            )
            result[idx] = joined
    return result
