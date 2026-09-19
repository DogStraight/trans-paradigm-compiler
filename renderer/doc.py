"""
doc.py — Doc IR (漂亮打印机中间表示)

基于 Wadler "A prettier printer" (2003) / Leijen "Wadler-Lindig" 模型。

Doc 是纯数据结构，不执行任何渲染逻辑。
布局算法 `layout(doc, width)` 将 Doc 树渲染为字符串。

Doc: renderer/renderer_architecture.md（Doc IR 原语与 layout 算法）
"""

from dataclasses import dataclass
from typing import Sequence, cast

# ── Doc 类型 ──


@dataclass
class Doc:
    """Doc 基类"""

    pass


@dataclass
class Empty(Doc):
    """无内容"""

    pass


@dataclass
class Text(Doc):
    """字面量文本"""

    text: str


@dataclass
class Line(Doc):
    """
    软换行。
    flat 模式 → 一个空格
    broken 模式 → 换行 + 当前缩进 + 附加缩进
    """

    indent: int = 0


@dataclass
class Break(Doc):
    """
    硬换行。
    无论 flat/broken 都强制换行 + 当前缩进 + 附加缩进。
    """

    indent: int = 0


@dataclass
class HardBreak(Doc):
    """
    强制断行（三态换行的第三态）。
    与 `Break` 同为"永远换行"，但**额外强制所在组断开**：含它的 `group()`
    不再生成 Union（直接返回 broken 形态），且该节点保留在 doc 里，使
    嵌套外层同样被强制（Prettier propagateBreaks 语义的构造期实现，
    2026-09-17）。用途：语义上"这一行必须在此结束"的构造（如行尾注释后
    不得再接同行元素——否则回读时被并入注释文本）。
    """

    indent: int = 0


@dataclass
class LineBreak(Doc):
    """
    条件换行（尾部专用）。
    flat 模式 → 空字符串（不产生空格）
    broken 模式 → 换行 + 当前缩进 + 附加缩进
    """

    indent: int = 0


@dataclass
class Concat(Doc):
    """顺序拼接"""

    docs: list[Doc]


@dataclass
class Nest(Doc):
    """
    缩进偏移。
    对 Nest 内部的所有 Line/Break 产生的新行增加 indent 格缩进。
    """

    indent: int
    doc: Doc


@dataclass
class Align(Doc):
    """
    绝对列对齐（Prettier align 语义，ADR-0006 阶段 2 新增）。

    除首行外，所有换行的缩进列 = max(当前缩进列, align)。
    首行不受影响（仍从当前列渲染）。
    与 Nest（相对偏移）互补：Align 设绝对列，内部嵌套 Nest 仍相对偏移。

    典型用途：跨行对齐（如端口声明 name 列）——group 二元模型表达不了
    的"组内列宽统一"，由 Align 给出基准列。
    """

    align: int
    doc: Doc


@dataclass
class Fill(Doc):
    """
    流式折行（Prettier fill 语义，ADR-0006 阶段 2 新增）。

    docs 是 内容/分隔符 交替序列：[item0, sep0, item1, sep1, ...]。
    逐元素贪心放置：
      - 分隔符（通常为 Line）：当前行放得下 → 空格；放不下 → 换行 + 缩进
      - 内容项：放不下时换行后再放
    与 group（整体二选一）不同：fill 是逐元素决策，可产生"折了几行、
    其余保持一行"的中间态。
    """

    docs: list[Doc]


@dataclass
class LineSuffix(Doc):
    """
    行尾锚定（Prettier lineSuffix 语义，ADR-0006 阶段 2 新增）。

    内容（通常为行尾注释文本）推迟到"下一个换行点之前"输出：
      Concat([a, LineSuffix("// note"), b, Line(), c]) →
      渲染为 "a b // note\nc"（suffix 跨过 b 锚定在行尾）。

    layout() 入口先经 _resolve_line_suffix 重写为
    Concat 内换行前的 Text，_best 内核无感知。
    与 inline_comment.py（现仅 tpc marker 内部通道）互补：前者是 Doc
    一等公民，后者是渲染后字符串级后处理。
    """

    text: str


@dataclass
class Prefix(Doc):
    """
    首行缩进 + 后续行 Nest 的统一原语。

    等价于 Concat([Text(indent 空格), Nest(indent, doc)])，
    但语义更清晰：
    - 第一行文本前插入 indent 个空格
    - 后续所有 Line/Break 换行时增加 indent 格缩进
    """

    indent: int
    doc: Doc


@dataclass
class Union(Doc):
    """
    二象性选择。
    flat = 压成一行的版本
    broken = 保留换行的版本
    layout 算法选择能适应当前剩余宽度的版本。
    """

    flat: Doc
    broken: Doc


@dataclass
class Pad(Doc):
    """
    对齐 padding（Veryl Pad 语义，渲染层深读闭环）。

    无条件输出 width 个空格，计入 fits 宽度。
    flat/broken 均输出——对齐 padding 参与布局决策（fits 判定），
    使对齐不再依赖"渲染后处理"（世界 B column_align 的痛点）。
    """

    width: int = 0


@dataclass
class IfBreakPad(Doc):
    """
    断行对齐 padding（Veryl IfBreakPad 语义）。

    仅 broken 模式输出 width 个空格；flat 模式 → 空（0 计 fits）。
    典型用途：断行后补对齐（`aaaaaaaa   :` 的 ':' 前 padding 只在
    断行时出现，flat 时不该占位）。
    """

    width: int = 0


@dataclass
class IfFlatPad(Doc):
    """
    扁平对齐 padding（Veryl IfFlatPad 语义）。

    仅 flat 模式输出 width 个空格；broken 模式 → 空。
    计入 fits 宽度——flat 时对齐占位，超宽可强制 group 断行。
    """

    width: int = 0


# ── 辅助构造器 ──


def group(doc: Doc) -> Doc:
    """创建 group：Union(flatten(doc), doc)

    含 `HardBreak`（永远换行且强制所在组断开）时**不生成 Union**：直接返回
    broken 形态。硬换行沿嵌套向上传播——外层 `group()` 看到的是子结构返回的
    doc，子结构里保留的 HardBreak 同样让外层强制断开（Prettier
    propagateBreaks 的构造期实现）。
    """
    if _forces_break(doc):
        return doc
    return Union(flat=flatten(doc), broken=doc)


def _forces_break(doc: Doc) -> bool:
    """doc 直接子树内是否含 HardBreak（**不进嵌套 Union**——嵌套组有自己的
    权威；但它被强制断开时会把 HardBreak 保留在自己返回的 doc 里，见
    `group()`，故传播仍然成立）。
    """
    match doc:
        case HardBreak():
            return True
        case Concat(docs) | Fill(docs):
            return any(_forces_break(d) for d in docs)
        case Nest(_, d) | Align(_, d) | Prefix(_, d):
            return _forces_break(d)
        case _:
            return False


def flatten(doc: Doc) -> Doc:
    """
    将 doc 中的所有 Line 替换为 Text(" ")。
    Union 取 flat 分支。
    Break 保持不变（硬换行不被 flatten）。
    """
    match doc:
        case Empty():
            return doc
        case Text(_):
            return doc
        case Line():
            return Text(" ")
        case Break() | HardBreak():
            return doc
        case LineBreak():
            return Empty()  # flat 模式：消失
        case Concat(docs):
            return Concat([flatten(d) for d in docs])
        case Nest(i, d):
            return Nest(i, flatten(d))
        case Align(a, d):
            return Align(a, flatten(d))
        case Fill(docs):
            # fill 扁平化：分隔符（Line）→ 空格，内容拼接
            return Concat([flatten(d) for d in docs])
        case LineSuffix(text):
            # flat 模式：suffix 直接显示（跟在当前行尾）
            return Text(text)
        case Pad(width):
            # 恒输出：flat 保留 padding（对齐参与 fits）
            return Text(" " * width) if width else Empty()
        case IfBreakPad(_):
            # 仅 broken 输出：flat 模式消失
            return Empty()
        case IfFlatPad(width):
            # 仅 flat 输出：flat 保留 padding（计入 fits，超宽可强制断行）
            return Text(" " * width) if width else Empty()
        case Prefix(i, d):
            flat_inner = flatten(d)
            if isinstance(flat_inner, Empty):
                return Text(" " * i)
            return Concat([Text(" " * i), flat_inner])
        case Union(flat, _):
            return flatten(flat)
        case _:
            return doc


def nest(indent: int, doc: Doc) -> Doc:
    """缩进，嵌套空 Doc 时返回空"""
    if isinstance(doc, Empty):
        return doc
    return Nest(indent, doc)


# ── Layout 算法 ──


def _resolve_line_suffix(doc: Doc) -> Doc:
    """将 LineSuffix 内容推迟到下一个换行点之前（行尾锚定）。

    规则（Prettier lineSuffix 语义的 Doc 层实现）：
      - 遍历 Concat 序列，收集挂起的 suffix 文本；
      - 遇到 Line/Break/HardBreak/LineBreak（换行点）→ 先把挂起 suffix 作为
        Text 插入到换行前；
      - 序列结束仍有挂起 → 追加到序列尾（doc 末尾即行尾）；
      - Nest/Align/Prefix/Union 递归处理；Fill 内不跨项推迟
        （内容项内 LineSuffix 就地文本化）。
    """
    match doc:
        case LineSuffix(text):
            return Text(text)  # 顶层孤立 suffix：直接显示
        case Concat(docs):
            out: list[Doc] = []
            pending: list[str] = []
            for d in docs:
                if isinstance(d, LineSuffix):
                    pending.append(d.text)
                    continue
                resolved = _resolve_line_suffix(d)
                if isinstance(resolved, (Line, Break, HardBreak, LineBreak)):
                    if pending:
                        out.append(Text("".join(pending)))
                        pending = []
                    out.append(resolved)
                elif isinstance(resolved, Empty):
                    if pending:
                        # 子结构为空但 suffix 挂起：保留，等下一个换行点
                        continue
                else:
                    out.append(resolved)
            if pending:
                out.append(Text("".join(pending)))
            return Concat(out)
        case Nest(i, d):
            return Nest(i, _resolve_line_suffix(d))
        case Align(a, d):
            return Align(a, _resolve_line_suffix(d))
        case Prefix(i, d):
            return Prefix(i, _resolve_line_suffix(d))
        case Union(flat, broken):
            return Union(
                _resolve_line_suffix(flat), _resolve_line_suffix(broken)
            )
        case Fill(docs):
            # Fill 内分隔符是换行点：suffix 若在内容项里，就地显示
            return Fill([_resolve_line_suffix(d) for d in docs])
        case _:
            return doc


def layout(doc: Doc, max_width: int = 80) -> str:
    """
    宽度感知的 Doc → 字符串渲染。

    算法：best(w, k, doc)
    w = 最大行宽
    k = 当前缩进列
    """
    # 布局辅助查询（_flat_w/_has_hardline/_has_break）单次 layout 内记忆化：
    # doc 树每次渲染重建（id 可复用），入口清缓存防止跨代误命中。
    _clear_layout_cache()
    # 先落行尾注释，再挤掉 HardBreak 之后紧邻的条件断（避免叠加出空行）
    resolved = _drop_break_after_hardbreak(_resolve_line_suffix(doc))
    return _best(max_width, 0, resolved)


def _break_str(k: int, indent: int) -> str:
    """断行原语统一形态：换行 + 绝对缩进列（k = 当前缩进列，indent = 附加级）。"""
    return "\n" + " " * (k + indent)


def _row_width(docs: Sequence[Doc], index: int) -> int:
    """第 index 项**同行**前后兄弟的 flat 宽度合计 → Union 判定预算。

    只有换行点之前的兄弟还在本行，故两侧累加都遇含断行的兄弟即停
    （`_has_break` 软硬断行都算）。本项自身不计入（预算只描述"将占的宽度"）。
    """
    before = 0
    for sibling in reversed(docs[:index]):
        if _has_break(sibling):
            break  # 更早的兄弟在换行点之前（不在本行）
        before += _flat_w(sibling)
    rest = 0
    for sibling in docs[index + 1 :]:
        if _has_break(sibling):
            break  # 换行点后的兄弟在新行（不在本行）
        rest += _flat_w(sibling)
    return before + rest


def _best_concat(w: int, k: int, docs: Sequence[Doc]) -> str:
    """Concat：逐项渲染，顺带维护行状态（当前行是否只余缩进 / 结束本行的断行类型）。

    行状态用途：当前行已空且由**非硬**断行结束时，子项开头的硬换行是冗余
    （父布局已在此断行）——不去会叠出纯空白行（三元 `? :` 断行 + 注释前硬换行
    = 空行）。连续 HardBreak 是显式空行惯例（tail_break 等），不由本路径挤除。
    每项的 budget = 同行前后兄弟宽度（`_row_width`）。
    """
    result: list[str] = []
    line_empty = False
    ended_by_hard = False
    for i, d in enumerate(docs):
        if line_empty and not ended_by_hard:
            d = _strip_leading_hardbreak(d)
        s = _best(w, k, d, _row_width(docs, i))
        result.append(s)
        if "\n" in s:
            line_empty = s.rsplit("\n", 1)[1].strip() == ""
            ended_by_hard = _ends_with_hardbreak(d)
        elif s.strip():
            line_empty = False
    return "".join(result)


def _best_union(w: int, k: int, flat: Doc, broken: Doc, budget: int) -> str:
    """Union：flat 版首行宽度 ≤ 剩余预算（w - k - budget，budget 含本项之后兄弟
    宽度——continuation 感知）则取 flat，否则回退 broken。
    """
    flat_s = _best(w, k, flat, budget)
    first_line = flat_s.split("\n")[0] if flat_s else ""
    if len(first_line) <= w - k - budget:
        return flat_s
    return _best(w, k, broken, budget)


def _best(w: int, k: int, doc: Doc, budget: int = 0) -> str:
    """核心布局函数：返回渲染后的字符串

    budget = 本项之后同层兄弟的 flat 宽度（到首个硬 break 为止）。
    仅 Union 的 flat 判定使用（预算 = w - k - budget）——防止
    "group 单独 fits、组合 continuation 溢出"（Veryl fits_flat
    语义）。渲染路径本身不累计列状态（文本宽度事后可量）。

    按 Doc 变体分派；多行的两处（Concat 的行状态机、Union 的 flat 判定）
    见 `_best_concat` / `_best_union`。
    """
    match doc:
        case Empty():
            return ""

        case Text(s):
            return s

        case Line(indent=i):
            return _break_str(k, i)

        case Break(indent=i):
            return _break_str(k, i)

        case HardBreak(indent=i):
            return _break_str(k, i)

        case LineBreak(indent=i):
            return _break_str(k, i)  # broken 模式：换行

        case Concat(docs):
            return _best_concat(w, k, docs)

        case Nest(i, d):
            return _best(w, k + i, d, budget)

        case Align(a, d):
            # 后续行缩进列 = max(当前缩进, 对齐列)；首行不受影响
            return _best(w, max(k, a), d, budget)

        case Fill(docs):
            return _fill(w, k, docs)

        case Prefix(i, d):
            return " " * i + _best(w, k + i, d, budget)

        case Union(flat, broken):
            return _best_union(w, k, flat, broken, budget)

        case Pad(width):
            # 恒输出（flat/broken 均输出，对齐参与布局）
            return " " * width

        case IfBreakPad(width):
            # 仅 broken 模式输出（Union 选 broken 时走到这里）
            return " " * width

        case IfFlatPad(_):
            # 仅 flat 模式输出；broken 模式消失（flat 分支已输出）
            return ""

        case _:
            return ""

# ── 布局辅助查询的 per-layout 记忆化 ──────────────────────────────
# _flat_w/_has_hardline/_has_break 是纯 doc 依赖的递归查询，_best 的
# Concat 兄弟预算计算对同一子树反复调用（无缓存 = O(n²) 重复全遍历）。
# Doc 是 immutable dataclass，同一次 layout 内 id(doc) 稳定 → 按键
# (id(doc), tag) 记忆化；doc 树每次渲染重建（id 可复用），layout() 入口
# 清缓存防跨代误命中。缓存是纯优化，命中错误只影响性能不影响正确性。
_LAYOUT_CACHE: dict[tuple[int, int], object] = {}

# 记忆化标签（缓存键第二项）：同一 doc 的不同查询各占独立槽位
_BREAK_QUERY_HARDLINE = 1  # `_has_hardline`：只认 Break/HardBreak/LineBreak
_BREAK_QUERY_LINE = 2      # `_has_break`：连软换行 Line 也算


def _clear_layout_cache() -> None:
    _LAYOUT_CACHE.clear()


def _ends_with_hardbreak(doc: Doc) -> bool:
    """doc 末尾最后叶子是否 HardBreak（沿 Concat/Nest/Align/Prefix 下钻）。

    Union（含嵌套组）返回 False——嵌套组自行决定断开与否，不参与挤除。
    """
    match doc:
        case HardBreak():
            return True
        case Concat(docs):
            return bool(docs) and _ends_with_hardbreak(docs[-1])
        case Nest(_, d) | Align(_, d) | Prefix(_, d):
            return _ends_with_hardbreak(d)
        case _:
            return False


def _strip_leading_hardbreak(doc: Doc) -> Doc:
    """去掉 doc 开头的硬换行（当前行已空 → 该断行冗余，防叠出空行）。

    沿 Concat/Nest/Align/Prefix 下钻到首个叶子：首叶为 HardBreak 则去掉。
    空行惯例（连续 `Break`）不经此路径，不受影响。
    """
    if isinstance(doc, HardBreak):
        return Empty()
    if isinstance(doc, Concat):
        if doc.docs and isinstance(doc.docs[0], HardBreak):
            rest = doc.docs[1:]
            return Concat(rest) if rest else Empty()
        return doc
    if isinstance(doc, Nest):
        inner = _strip_leading_hardbreak(doc.doc)
        return Empty() if isinstance(inner, Empty) else Nest(doc.indent, inner)
    if isinstance(doc, Align):
        inner = _strip_leading_hardbreak(doc.doc)
        return Empty() if isinstance(inner, Empty) else Align(doc.align, inner)
    if isinstance(doc, Prefix):
        inner = _strip_leading_hardbreak(doc.doc)
        return Empty() if isinstance(inner, Empty) else Prefix(doc.indent, inner)
    return doc


def _drop_break_after_hardbreak(doc: Doc) -> Doc:
    """`HardBreak` 之后紧邻的**条件断**（LineBreak）不再产生新行。

    条件断的语义是"本组断开时在此断"；前一项已强制断行（HardBreak）时
    "此处断行"与那处断行是同一处——叠加会多出一个空行（典型：列表末项行尾
    注释的 HardBreak + 模块头 `)` 前的 `{ break = true }`）。
    只挤掉条件断：软断（Line）与硬断（Break）不动——`tail_break` 用连续
    `Break` 表达空行，不能被挤。
    """
    match doc:
        case Concat(docs):
            out: list[Doc] = []
            for d in docs:
                resolved = _drop_break_after_hardbreak(d)
                if (
                    isinstance(resolved, LineBreak)
                    and out
                    and _ends_with_hardbreak(out[-1])
                ):
                    continue
                out.append(resolved)
            return Concat(out)
        case Nest(i, d):
            return Nest(i, _drop_break_after_hardbreak(d))
        case Align(a, d):
            return Align(a, _drop_break_after_hardbreak(d))
        case Prefix(i, d):
            return Prefix(i, _drop_break_after_hardbreak(d))
        case Union(flat, broken):
            return Union(
                _drop_break_after_hardbreak(flat),
                _drop_break_after_hardbreak(broken),
            )
        case Fill(docs):
            return Fill([_drop_break_after_hardbreak(d) for d in docs])
        case _:
            return doc


def _has_hardline(doc: Doc) -> bool:
    """doc（flat 化后）是否含硬换行（Break/LineBreak，不含软换行 Line）。"""
    return _doc_has_break(doc, _BREAK_QUERY_HARDLINE)


def _has_break(doc: Doc) -> bool:
    """doc 是否含换行点（Line/Break/LineBreak）——Union 首行判定截断用。"""
    return _doc_has_break(doc, _BREAK_QUERY_LINE)


def _doc_has_break(doc: Doc, query: int) -> bool:
    """doc 是否含换行点（递归下降；query 决定 `Line()` 算不算命中）。

    纯 doc 依赖的递归查询，按 (doc, query) 记忆化（见 `_LAYOUT_CACHE`）——
    同一 doc 两种查询结果不同（硬换行 / 含软换行点），**不可共用缓存槽位**。
    """
    key = (id(doc), query)
    if key in _LAYOUT_CACHE:
        return cast(bool, _LAYOUT_CACHE[key])
    match doc:
        case Line() if query == _BREAK_QUERY_LINE:
            result = True
        case Break() | HardBreak() | LineBreak():
            result = True
        case Concat(docs):
            result = any(_doc_has_break(d, query) for d in docs)
        case Nest(_, d) | Align(_, d) | Prefix(_, d):
            result = _doc_has_break(d, query)
        case Union(flat, _):
            result = _doc_has_break(flat, query)
        case Fill(docs):
            result = any(_doc_has_break(d, query) for d in docs)
        case _:
            result = False
    _LAYOUT_CACHE[key] = result
    return result


def _flat_w(doc: Doc) -> int:
    """doc 的 flat 版本宽度（纯计算，不走 _best——避免 _best↔_flat_width 互递归）。

    flat 版语义：Line → 1 空格；Break/LineBreak 保留（硬换行）；
    Pad/IfFlatPad 计宽；IfBreakPad 0 宽。
    纯 doc 依赖的递归查询，per-layout 记忆化（见 _LAYOUT_CACHE）——
    _best 的 Concat 兄弟预算计算对同一子树反复查询，无缓存时 O(n²)
    重复遍历（3000 行级真实语料实测 _flat_w 200 万次 / _has_hardline
    1000 万次调用，渲染占单遍管线 ~60%）。
    """
    key = (id(doc), 0)
    if key in _LAYOUT_CACHE:
        return cast(int, _LAYOUT_CACHE[key])
    match doc:
        case Text(s):
            result = len(s)
        case Line():
            result = 1  # flat 模式：空格
        case Concat(docs):
            total = 0
            for d in docs:
                total += _flat_w(d)
                if _has_hardline(d):
                    break
            result = total
        case Nest(_, d) | Align(_, d) | Prefix(_, d):
            result = _flat_w(d)
        case Union(flat, _):
            result = _flat_w(flat)
        case Fill(docs):
            result = sum(_flat_w(d) for d in docs)
        case Pad(width) | IfFlatPad(width):
            result = width
        case IfBreakPad(_):
            result = 0
        case _:
            result = 0
    _LAYOUT_CACHE[key] = result
    return result


def _flat_width(doc: Doc) -> int:
    """doc 的 flat 版本宽度（不含换行的行宽）。

    fill 贪心决策用：内容项/分隔符的 flat 宽度 = 渲染后最后一行长度。
    """
    s = _best(1 << 30, 0, flatten(doc))
    return len(s.split("\n")[-1])


def _fill(w: int, k: int, docs: list[Doc]) -> str:
    """Fill 布局：内容/分隔符交替序列的贪心放置。

    docs = [item0, sep0, item1, sep1, ...]。
    每对 (sep, next_item)：当前行放得下 → sep 呈 flat（空格）；
    放不下 → sep 呈 broken（换行 + 缩进），next_item 换行后放置。
    """
    out: list[str] = []
    col = 0  # 当前行已用宽度（相对 k）
    n = len(docs)
    for i, d in enumerate(docs):
        if i % 2 == 0:
            # 内容项
            flat_w = _flat_width(d)
            out.append(_best(w, k, d))
            col += flat_w
        else:
            # 分隔符（Line 通常）：放得下 → 空格，放不下 → 换行
            if i + 1 >= n:
                out.append(_best(w, k, flatten(d)))
                continue
            sep_w = _flat_width(d)
            nxt_w = _flat_width(docs[i + 1])
            if col + sep_w + nxt_w <= w - k:
                out.append(_best(w, k, flatten(d)))
                col += sep_w
            else:
                out.append("\n" + " " * k)
                col = 0
    return "".join(out)


def _fits_fixed_len(d: Doc) -> int | None:
    """定宽子项的列宽：Text 字数 / Pad·IfFlatPad 宽度 / IfBreakPad 的 0；非定宽 → None。"""
    if isinstance(d, Text):
        return len(d.s)
    if isinstance(d, (Pad, IfFlatPad)):
        return d.width
    if isinstance(d, IfBreakPad):
        return 0  # flat 布局 0 宽
    return None


def _fits_concat(w: int, docs: Sequence[Doc]) -> bool:
    """Concat 首行 fit 检查：逐个累加列宽，遇断行即"当前行已结束"→ True。

    与原实现逐字同源，两处保守语义**刻意保留**（改动即行为变化）：
    - `Nest`/`Prefix`/`Union` 子项递归判定后**立即返回**，不再累加其后的兄弟
      宽度（col 递归后不可知）；
    - `Concat` 子项走内层扫描 `_fits_concat_inner`，内层未出结论时回到外层继续
      （列宽沿用）。

    定宽子项（Text/Pad/IfBreakPad/IfFlatPad）在此直接累加，其余分派给 `_fits_step`。
    """
    col = 0
    for d in docs:
        if col > w:
            return False
        length = _fits_fixed_len(d)
        if length is not None:
            col += length
            if col > w:
                return False
            continue
        verdict, col = _fits_step(w, col, d)
        if verdict is not None:
            return verdict
    return col <= w


def _fits_step(w: int, col: int, d: Doc) -> tuple[bool | None, int]:
    """非定宽子项的 fit 推进：返回 (结论, 列宽)；结论 None = 继续下一个子项。"""
    match d:
        case Line() | Break() | HardBreak():
            return True, col
        case Nest(_, inner):
            # Nest 不影响 fits（缩进只影响后续行）；递归后 col 不可知 → 保守收口
            return _fits(w - col, inner), col
        case Union(flat, _):
            return _fits(w - col, flat), col
        case Prefix(i, inner):
            col += i
            if col > w:
                return False, col
            return _fits(w - col, inner), col
        case Concat(inner_docs):
            return _fits_concat_inner(w, col, inner_docs)
        case _:
            return True, col


def _fits_concat_inner(
    w: int, col: int, docs: Sequence[Doc]
) -> tuple[bool | None, int]:
    """Concat 子项的内层扫描（**与 `_fits_concat` 刻意不同**，别合并成一份）。

    返回 (结论, 列宽)；结论 None = 内层未出结论 → 回外层继续（列宽沿用）。
    差异在"未知子项"：内层对其做一次 `_fits` 判定，外层按保守取 True——这是
    与原实现同源的行为，不是笔误。
    """
    for d in docs:
        if col > w:
            return False, col
        match d:
            case Line() | Break() | HardBreak():
                return True, col
            case Text(s):
                col += len(s)
            case _:
                if not _fits(w - col, d):
                    return False, col
                return True, col
    return None, col


def _fits(w: int, doc: Doc) -> bool:
    """
    检查 doc 的 flat 版本是否能放入 w 列宽。
    只检查第一行。

    按 Doc 变体分派（首行宽度语义见 `_fits_concat`；Nest/Align 只影响后续行
    缩进，不影响首行判定）。
    """
    if w < 0:
        return False
    match doc:
        case Empty():
            return True
        case Text(s):
            return len(s) <= w
        case Line():
            return True  # 换行 = 当前行已结束
        case Break() | HardBreak():
            return True
        case Concat(docs):
            return _fits_concat(w, docs)
        case Nest(_, d):
            return _fits(w, d)
        case Align(_, d):
            # Align 只影响后续行缩进，不影响首行 fits 判断
            return _fits(w, d)
        case Fill(docs):
            # Fill 首行 = flat 版本（全在一行）
            return _fits(w, Concat([flatten(d) for d in docs]))
        case Prefix(i, d):
            return _fits(w - i, d)
        case Union(flat, _):
            return _fits(w, flat)
        case Pad(width) | IfFlatPad(width):
            # 恒输出 / flat 输出：计入宽度
            return width <= w
        case IfBreakPad(_):
            # 仅 broken 输出：flat 布局 0 宽
            return True
        case _:
            return True

