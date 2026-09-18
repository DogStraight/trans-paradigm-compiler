"""checks 插件族共用助手 — 赋值目标信号名 / 常量字面量与表达式求值。

这里的函数原先在 `always_check` / `case_check` / `latch_check` / `width_check`
各存一份同体或近同体实现（本轮外部审计"结构重复"命中），收敛到本模块一份。
结构知识（`Identifier` / `SelectExpr` / `HierExpr` 形态、Verilog 字面量写法、
参数名求值域）留在**插件层**，引擎不参与。

Doc: grammar/verilog/plugins/checks/README.md（插件族共用助手）
"""
from core.define import Node


def target_sig(target: Node | None) -> str | None:
    """赋值目标 → 根信号名（Identifier 本体 / SelectExpr 取 base /
    HierExpr 取首段；拼接目标 → None 保守跳过）。
    """
    if not isinstance(target, Node):
        return None
    name = target.node_name
    if name == "Identifier":
        return getattr(target, "content", "") or None
    if name == "SelectExpr":
        return target_sig(getattr(target, "base", None))
    if name == "HierExpr":
        parts = getattr(target, "parts", None) or []
        if parts and isinstance(parts[0], Node):
            return getattr(parts[0], "content", "") or None
        return None
    return None


def const_value(text: str) -> tuple[int, int] | None:
    """case 臂常量文本 → (值, 位宽)；变量/通配符/x/z → None。

    位宽取显式尺寸（`8'hFF` → 8）；无尺寸 → 值的最小位宽（0 → 1 位）。
    单字符 `'0`/`'1`/`'x`/`'z`/`'?` 是**填充/通配符**，不算覆盖 case 臂。
    """
    t = (text or "").strip()
    if "'" not in t:
        if not t.isdigit():
            return None
        v = int(t)
        return (v, v.bit_length() if v else 1)
    body = t.split("'", 1)[1]
    if not body:
        return None
    if body[0] in "sS":
        body = body[1:]
    if not body:
        return None
    if len(body) == 1 and body in "01xXzZ?":
        return None  # 填充/通配符常量不算覆盖
    base_ch = body[0].lower()
    if base_ch not in "bohd":
        return None
    digits = body[1:].replace("_", "")
    if not digits or any(c in "xXzZ?" for c in digits):
        return None
    try:
        v = int(digits, {"b": 2, "o": 8, "h": 16, "d": 10}[base_ch])
    except ValueError:
        return None
    w = int(t.split("'", 1)[0]) if t.split("'", 1)[0].strip().isdigit() \
        else (v.bit_length() if v else 1)
    return (v, w)


def const_tokenize(text: str, params: dict | None = None) -> list | None:
    """常量表达式 tokenize：数字 / 运算符 / 括号 /（有参数表时）参数名。

    参数名就地解析：值须为 int 或**纯数字字符串**，否则该标识符不可判。
    `params` 为空 → 标识符一律不可判（纯数字域用法）。
    未知字符或不可判标识符 → None（保守）。
    """
    params = params or {}
    toks: list = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            toks.append(("num", int(text[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            v = params.get(text[i:j])
            if v is None:
                return None
            if isinstance(v, str):
                if not v.strip().isdigit():
                    return None  # 参数默认值非纯数字 → 不可判
                toks.append(("param", int(v.strip())))
            else:
                toks.append(("param", v))
            i = j
            continue
        if ch in "+-*/%()":
            toks.append((ch, ch))
            i += 1
            continue
        return None
    toks.append(("eof", ""))
    return toks


class _ConstExprParser:
    """整数常量表达式递归下降解析器（游标即状态，故用类而非闭包）。"""

    def __init__(self, toks: list) -> None:
        self.toks = toks
        self.pos = 0

    def parse(self) -> int | None:
        """整串求值：必须吃到 eof，否则不可判。"""
        val = self._expr()
        if val is None or self._peek()[0] != "eof":
            return None
        return val

    def _peek(self) -> tuple:
        return self.toks[self.pos] if self.pos < len(self.toks) else ("eof", "")

    def _advance(self) -> tuple:
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def _expr(self) -> int | None:
        """加减（左结合）。"""
        left = self._term()
        if left is None:
            return None
        while self._peek()[0] in ("+", "-"):
            op = self._advance()[0]
            right = self._term()
            if right is None:
                return None
            left = left + right if op == "+" else left - right
        return left

    def _term(self) -> int | None:
        """乘除模（左结合）；除/模零 → 不可判。"""
        left = self._factor()
        if left is None:
            return None
        while self._peek()[0] in ("*", "/", "%"):
            op = self._advance()[0]
            right = self._factor()
            if right is None:
                return None
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    return None
                left = left // right
            else:
                if right == 0:
                    return None
                left = left % right
        return left

    def _factor(self) -> int | None:
        """一元 +/- 链、括号、数字、参数。"""
        t = self._peek()
        if t[0] == "-":
            self._advance()
            v = self._factor()
            return -v if v is not None else None
        if t[0] == "+":
            self._advance()
            return self._factor()
        if t[0] == "(":
            self._advance()
            v = self._expr()
            if v is None or self._peek()[0] != ")":
                return None
            self._advance()
            return v
        if t[0] in ("num", "param"):
            self._advance()
            return t[1]
        return None


def const_eval(text: str, params: dict | None = None) -> int | None:
    """常量表达式求值 → 整数｜None（不可判，保守）。

    递归下降（不用 `eval`——源码文本求值有 RCE 风险）：expr → term(+-) →
    factor(* / %) → 一元/括号/常量；数域为**整数**（`/` 与 `%` 取整除、除零
    → None）。`params` 给出参数名 → 值时可参与求值（如 `WIDTH-1`），
    否则标识符即不可判。
    """
    toks = const_tokenize(text, params)
    if toks is None:
        return None
    return _ConstExprParser(toks).parse()
