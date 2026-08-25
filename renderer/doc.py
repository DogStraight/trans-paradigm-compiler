"""
doc.py — Doc IR (漂亮打印机中间表示)

基于 Wadler "A prettier printer" (2003) / Leijen "Wadler-Lindig" 模型。

Doc 是纯数据结构，不执行任何渲染逻辑。
布局算法 `layout(doc, width)` 将 Doc 树渲染为字符串。

Doc: docs/renderer_architecture.md（Doc IR 原语与 layout 算法）/ docs/decisions/0006-renderer-improve-roadmap.md（改进路线）
"""

from dataclasses import dataclass

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
    与既有 inline_comment.py 锚点回插互补：前者是 Doc 一等公民，
    后者是渲染后字符串级后处理。
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


# ── 辅助构造器 ──


def group(doc: Doc) -> Doc:
    """创建 group：Union(flatten(doc), doc)"""
    return Union(flat=flatten(doc), broken=doc)


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
        case Break():
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
      - 遇到 Line/Break/LineBreak（换行点）→ 先把挂起 suffix 作为
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
                if isinstance(resolved, (Line, Break, LineBreak)):
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
    return _best(max_width, 0, _resolve_line_suffix(doc))


def _best(w: int, k: int, doc: Doc) -> str:
    """核心布局函数：返回渲染后的字符串"""
    match doc:
        case Empty():
            return ""

        case Text(s):
            return s

        case Line(indent=i):
            return "\n" + " " * (k + i)

        case Break(indent=i):
            return "\n" + " " * (k + i)

        case LineBreak(indent=i):
            return "\n" + " " * (k + i)  # broken 模式：换行

        case Concat(docs):
            result: list[str] = []
            for d in docs:
                s = _best(w, k, d)
                result.append(s)
            return "".join(result)

        case Nest(i, d):
            return _best(w, k + i, d)

        case Align(a, d):
            # 后续行缩进列 = max(当前缩进, 对齐列)；首行不受影响
            return _best(w, max(k, a), d)

        case Fill(docs):
            return _fill(w, k, docs)

        case Prefix(i, d):
            return " " * i + _best(w, k + i, d)

        case Union(flat, broken):
            # 尝试 flat 版本
            flat_s = _best(w, k, flat)
            first_line = flat_s.split("\n")[0] if flat_s else ""
            if len(first_line) <= w - k:
                return flat_s
            # flat 超宽，回退到 broken
            return _best(w, k, broken)

        case _:
            return ""


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


def _fits(w: int, doc: Doc) -> bool:
    """
    检查 doc 的 flat 版本是否能放入 w 列宽。
    只检查第一行。
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
        case Break():
            return True
        case Concat(docs):
            col = 0
            for d in docs:
                if col > w:
                    return False
                match d:
                    case Line():
                        return True
                    case Break():
                        return True
                    case Text(s):
                        col += len(s)
                        if col > w:
                            return False
                    case Nest(_, inner):
                        # Nest 不影响 fits（缩进只影响后续行）
                        if not _fits(w - col, inner):
                            return False
                        # 递归后不确定 col，用保守估算
                        return True
                    case Prefix(i, inner):
                        col += i
                        if col > w:
                            return False
                        return _fits(w - col, inner)
                    case Union(flat, _):
                        if not _fits(w - col, flat):
                            return False
                        return True
                    case Concat(inner_docs):
                        for inner_d in inner_docs:
                            if col > w:
                                return False
                            match inner_d:
                                case Line() | Break():
                                    return True
                                case Text(s):
                                    col += len(s)
                                case _:
                                    if not _fits(w - col, inner_d):
                                        return False
                                    return True
                    case _:
                        return True
            return col <= w
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
        case _:
            return True
