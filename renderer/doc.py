"""
doc.py — Doc IR (漂亮打印机中间表示)

基于 Wadler "A prettier printer" (2003) / Leijen "Wadler-Lindig" 模型。

Doc 是纯数据结构，不执行任何渲染逻辑。
布局算法 `layout(doc, width)` 将 Doc 树渲染为字符串。
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

_EMPTY = Empty()


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


def layout(doc: Doc, max_width: int = 80) -> str:
    """
    宽度感知的 Doc → 字符串渲染。

    算法：best(w, k, doc)
    w = 最大行宽
    k = 当前缩进列
    """
    return _best(max_width, 0, doc)


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
        case Prefix(i, d):
            return _fits(w - i, d)
        case Union(flat, _):
            return _fits(w, flat)
        case _:
            return True
