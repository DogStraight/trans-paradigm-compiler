"""_asm.py — c4 汇编生成插件（c4 AST → c4 VM 指令集）。

对应 rswier/c4 的 c4.c 编译逻辑（expr/stmt/声明 → 指令发射，上游 github.com/rswier/c4），
输出 c4 的 VM 汇编文本（LEA/IMM/JMP/JSR/BZ/BNZ/ENT/ADJ/LEV/LI/LC/SI/SC/PSH/
OR/XOR/AND/EQ/NE/LT/GT/LE/GE/SHL/SHR/ADD/SUB/MUL/DIV/MOD）。

以 TransformPlugin 注册（@register_plugin），process 守卫根节点为 c4 的
Program 才生成汇编（Verilog 等其它语言 AST 原样返回，互不干扰）。
产出：AsmProgram 节点（sub_node = AsmLine，text = 单条指令），由 renderer 渲染。
"""

from typing import Any

from core.define import Node
from analyzer.scope import Scope
from transform.engine import TransformPlugin, register_plugin

# ── c4 类型常量（对应 c4.c 的 CHAR/INT/PTR）────────────────────
CHAR, INT, PTR = 0, 1, 2
# 符号类别
GLO, FUN, LOC, NUM = "glo", "fun", "loc", "num"

_OPCODE_NAMES = [
    "LEA", "IMM", "JMP", "JSR", "BZ", "BNZ", "ENT", "ADJ", "LEV",
    "LI", "LC", "SI", "SC", "PSH",
    "OR", "XOR", "AND", "EQ", "NE", "LT", "GT", "LE", "GE",
    "SHL", "SHR", "ADD", "SUB", "MUL", "DIV", "MOD",
    "OPEN", "READ", "CLOS", "PRTF", "MALC", "FREE", "MSET", "MCMP", "EXIT",
]
# 有操作数的指令（对应 c4.c 的 <= ADJ 打印带操作数）
_HAS_ARG = {"LEA", "IMM", "JMP", "JSR", "BZ", "BNZ", "ENT", "ADJ"}


class _Emitter:
    """指令发射器（标签回填）。"""

    def __init__(self) -> None:
        self.code: list[tuple[str, Any]] = []  # (opcode, arg)  arg=None 表示无操作数
        self._label_pos: dict[str, int] = {}
        self._pending: list[tuple[int, str]] = []  # (index, label) 待回填

    def emit(self, op: str, arg: Any = None) -> None:
        self.code.append((op, arg))

    def label(self, name: str) -> None:
        self._label_pos[name] = len(self.code)

    def emit_jump(self, op: str, label: str) -> None:
        """发射跳转，目标用标签（回填）。"""
        self.code.append((op, None))
        self._pending.append((len(self.code) - 1, label))

    def resolve(self) -> None:
        for idx, label in self._pending:
            self.code[idx] = (self.code[idx][0], self._label_pos[label])

    def lines(self) -> list[str]:
        out = []
        for op, arg in self.code:
            if op in _HAS_ARG and arg is not None:
                out.append(f"  {op:4} {arg}")
            else:
                out.append(f"  {op}")
        return out


class _C4Compiler:
    """c4 编译器：AST + 符号表 → 指令。"""

    def __init__(self) -> None:
        self.symbols: dict[str, dict] = {}  # name → {class, type, val}
        self._data_addr = 0  # 全局变量地址
        self._str_addr = 0  # 字符串池地址（独立于全局变量区之后）
        self._strings: list[str] = []
        self._label_n = 0
        self.emitter = _Emitter()

    # ── 符号表 ──
    def _declare(self, name: str, cls: str, ty: int, val: Any) -> None:
        self.symbols[name] = {"class": cls, "type": ty, "val": val}

    def _new_label(self) -> str:
        self._label_n += 1
        return f"L{self._label_n}"

    def _string_addr(self, s: str) -> int:
        """字符串入池，返回地址。"""
        if s not in self._strings:
            self._strings.append(s)
            self._str_addr += len(s) + 1
        idx = self._strings.index(s)
        base = self._data_addr + 4  # 全局变量区后
        return base + sum(len(x) + 1 for x in self._strings[:idx])

    # ── 表达式（值 → a 寄存器）──
    def expr(self, n: Node, loc: int) -> None:
        name = n.node_name
        if name == "Number":
            self.emitter.emit("IMM", self._int_value(n))
        elif name == "StringLit":
            s = self._str_value(n)
            self.emitter.emit("IMM", self._string_addr(s))
        elif name == "Identifier":
            self._expr_identifier(n, loc)
        elif name == "BinaryOp":
            self.expr(n.left, loc)
            self.emitter.emit("PSH")
            self.expr(n.right, loc)
            self.emitter.emit(self._binop(n.op))
        elif name == "UnaryOp":
            self._expr_unary(n, loc)
        elif name == "TernaryOp":
            self._expr_ternary(n, loc)
        elif name == "CallExpr":
            self._expr_call(n, loc)
        elif name == "IndexExpr":
            self._expr_index(n, loc)
        elif name == "ParenthesizedExpr":
            self.expr(n.expr, loc)
        elif name == "TypeCastExpr":
            self.expr(n.value, loc)
        elif name == "SizeofExpr":
            size = 4 if self._is_char_type(n.type_name) else 4
            self.emitter.emit("IMM", size)
        else:
            # 未知节点：尝试第一个子节点
            ch = list(n.iter_children())
            if ch:
                self.expr(ch[0], loc)
            else:
                self.emitter.emit("IMM", 0)

    def _int_value(self, n: Node) -> int:
        v = getattr(n, "value", None)
        if v is None:
            for c in n.iter_children():
                return self._int_value(c)
        if isinstance(v, Node):
            return self._int_value(v)
        if isinstance(v, str):
            try:
                return int(v, 0)
            except ValueError:
                return 0
        return int(v or 0)

    def _str_value(self, n: Node) -> str:
        v = getattr(n, "value", None)
        if isinstance(v, Node):
            return self._str_value(v)
        s = str(v or "")
        if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
            s = s[1:-1]
        return s

    def _is_char_type(self, type_name: Node) -> bool:
        base = getattr(type_name, "base", None)
        b = base.node_name if isinstance(base, Node) else base
        return "char" in str(b)

    def _expr_identifier(self, n: Node, loc: int) -> None:
        name = getattr(n, "content", None)
        if isinstance(name, Node):
            name = getattr(name, "content", None)
        if name is None:
            name = str(getattr(n, "content", ""))
        sym = self.symbols.get(str(name))
        if sym is None:
            # 未声明：按整数 0 处理（容错）
            self.emitter.emit("IMM", 0)
            return
        if sym["class"] == NUM:
            self.emitter.emit("IMM", sym["val"])
        elif sym["class"] == LOC:
            self.emitter.emit("LEA", loc - sym["val"])
            self.emitter.emit("LI" if sym["type"] == INT else "LC")
        elif sym["class"] == GLO:
            self.emitter.emit("IMM", sym["val"])
            self.emitter.emit("LI" if sym["type"] == INT else "LC")

    def _expr_unary(self, n: Node, loc: int) -> None:
        op = getattr(n, "op", "")
        operand = getattr(n, "operand", None)
        if op == "!":
            self.expr(operand, loc)
            self.emitter.emit("PSH")
            self.emitter.emit("IMM", 0)
            self.emitter.emit("EQ")
        elif op == "~":
            self.expr(operand, loc)
            self.emitter.emit("PSH")
            self.emitter.emit("IMM", -1)
            self.emitter.emit("XOR")
        elif op == "-":
            self.expr(operand, loc)
            self.emitter.emit("PSH")
            self.emitter.emit("IMM", -1)
            self.emitter.emit("MUL")
        elif op in ("*", "&"):
            # 解引用/取址（简化为直接取值）
            self.expr(operand, loc)
            if op == "*":
                self.emitter.emit("LI")
        elif op == "++":
            self._expr_pre_incdec(n, loc, 1)
        elif op == "--":
            self._expr_pre_incdec(n, loc, -1)
        else:
            self.expr(operand, loc)

    def _expr_pre_incdec(self, n: Node, loc: int, delta: int) -> None:
        operand = getattr(n, "operand", None)
        # 简化为立即数（完整 lvalue 自增留作扩展）
        self.expr(operand, loc)
        self.emitter.emit("PSH")
        self.emitter.emit("IMM", delta)
        self.emitter.emit("ADD")

    def _expr_ternary(self, n: Node, loc: int) -> None:
        cond = getattr(n, "cond", None)
        tv = getattr(n, "true_val", None)
        fv = getattr(n, "false_val", None)
        l1, l2 = self._new_label(), self._new_label()
        self.expr(cond, loc)
        self.emitter.emit_jump("BZ", l1)
        self.expr(tv, loc)
        self.emitter.emit_jump("JMP", l2)
        self.emitter.label(l1)
        self.expr(fv, loc)
        self.emitter.label(l2)

    def _expr_call(self, n: Node, loc: int) -> None:
        callee = getattr(n, "callee", None)
        fname = self._ident_text(callee)
        args = getattr(n, "args", None)
        arg_nodes = self._arg_list(args)
        # 实参从右往左压栈（c4 顺序：逐个 expr + PSH）
        for a in arg_nodes:
            self.expr(a, loc)
            self.emitter.emit("PSH")
        if fname in self.symbols and self.symbols[fname]["class"] == FUN:
            self.emitter.emit_jump("JSR", f"F{fname}")
        else:
            # 库函数（c4 syscalls）
            lib = self._lib_code(fname)
            self.emitter.emit("IMM", lib)
        if arg_nodes:
            self.emitter.emit("ADJ", len(arg_nodes))

    def _expr_index(self, n: Node, loc: int) -> None:
        base = getattr(n, "base", None)
        self.expr(base, loc)
        self.emitter.emit("PSH")
        idx = getattr(n, "indexes", None)
        # indexes 是 repeat 子节点列表，取第一个 Expression
        idx_node = self._first_expression(idx)
        if idx_node is not None:
            self.expr(idx_node, loc)
        else:
            self.emitter.emit("IMM", 0)
        self.emitter.emit("PSH")
        self.emitter.emit("IMM", 4)
        self.emitter.emit("MUL")
        self.emitter.emit("ADD")
        self.emitter.emit("LI")

    def _first_expression(self, node: Node | list | None):
        """从 repeat/indexes 结构取首个 Expression 节点。"""
        if node is None:
            return None
        if isinstance(node, list):
            for it in node:
                r = self._first_expression(it)
                if r is not None:
                    return r
            return None
        if isinstance(node, Node):
            if node.node_name == "Expression":
                return node
            for c in node.iter_children():
                r = self._first_expression(c)
                if r is not None:
                    return r
        return None

    def _arg_list(self, args: Node | None) -> list[Node]:
        """提取实参节点列表（健壮：不依赖 items 具体结构）。"""
        if args is None:
            return []
        out = []
        for ch in args.iter_children():
            if isinstance(ch, Node):
                out.append(ch)
        return out

    def _ident_text(self, node: Node | None) -> str:
        if node is None:
            return ""
        if isinstance(node, Node):
            c = getattr(node, "content", None)
            if c is not None:
                return str(c) if not isinstance(c, Node) else str(getattr(c, "content", ""))
            for ch in node.iter_children():
                r = self._ident_text(ch)
                if r:
                    return r
        return str(node)

    def _lib_code(self, name: str) -> int:
        libs = ["open", "read", "close", "printf", "malloc", "free", "memset", "memcmp", "exit"]
        return 100 + libs.index(name) if name in libs else 100

    def _binop(self, op: str) -> str:
        mapping = {
            "||": "OR", "&&": "AND", "|": "OR", "^": "XOR", "&": "AND",
            "==": "EQ", "!=": "NE", "<": "LT", ">": "GT", "<=": "LE", ">=": "GE",
            "<<": "SHL", ">>": "SHR", "+": "ADD", "-": "SUB",
            "*": "MUL", "/": "DIV", "%": "MOD",
        }
        return mapping.get(op, "ADD")

    # ── 语句 ──

    _STMT_NAMES = {
        "IfStmt", "WhileStmt", "ReturnStmt", "BlockStmt",
        "ExprStmt", "EmptyStmt", "VarDecl",
    }

    def _unwrap_stmt(self, node):
        """从 optional/seq/list 包装中解出实际语句节点（else_body 等）。"""
        if node is None:
            return None
        if isinstance(node, list):
            for it in node:
                r = self._unwrap_stmt(it)
                if r is not None:
                    return r
            return None
        if not isinstance(node, Node):
            return None
        if node.node_name in self._STMT_NAMES:
            return node
        for c in node.iter_children():
            r = self._unwrap_stmt(c)
            if r is not None:
                return r
        return None

    def stmt(self, n: Node, loc: int) -> None:
        name = n.node_name
        if name == "IfStmt":
            l1, l2 = self._new_label(), self._new_label()
            self.expr(n.cond, loc)
            self.emitter.emit_jump("BZ", l1)
            self.stmt(n.then_body, loc)
            self.emitter.emit_jump("JMP", l2)
            self.emitter.label(l1)
            eb = self._unwrap_stmt(getattr(n, "else_body", None))
            if eb is not None:
                self.stmt(eb, loc)
            self.emitter.label(l2)
        elif name == "WhileStmt":
            l1, l2 = self._new_label(), self._new_label()
            self.emitter.label(l1)
            self.expr(n.cond, loc)
            self.emitter.emit_jump("BZ", l2)
            self.stmt(n.body, loc)
            self.emitter.emit_jump("JMP", l1)
            self.emitter.label(l2)
        elif name == "ReturnStmt":
            v = getattr(n, "value", None)
            if v is not None:
                self.expr(v, loc)
            self.emitter.emit("LEV")
        elif name == "BlockStmt":
            for c in getattr(n, "sub_node", []) or []:
                self.stmt(c, loc)
        elif name == "ExprStmt":
            e = getattr(n, "expr", None)
            if e is not None:
                self._expr_stmt_assign(e, loc)
        elif name == "VarDecl":
            pass  # 局部声明：地址在函数入口统一分配
        elif name == "EmptyStmt":
            pass
        else:
            # 未知语句：递归处理子节点（容错）
            for c in n.iter_children():
                self.stmt(c, loc)

    def _expr_stmt_assign(self, e: Node, loc: int) -> None:
        """表达式语句（含赋值）：处理 BinaryOp '=' 的左值。"""
        if e.node_name == "BinaryOp" and getattr(e, "op", "") == "=":
            left = e.left
            self._lvalue_addr(left, loc)
            self.emitter.emit("PSH")
            self.expr(e.right, loc)
            ty = self._lvalue_type(left)
            self.emitter.emit("SC" if ty == CHAR else "SI")
        else:
            self.expr(e, loc)

    def _lvalue_addr(self, left: Node, loc: int) -> None:
        """发射左值地址（局部 LEA / 全局 IMM）。"""
        if left.node_name == "Identifier":
            name = self._ident_text(left)
            sym = self.symbols.get(name)
            if sym is None:
                self.emitter.emit("IMM", 0)
            elif sym["class"] == LOC:
                self.emitter.emit("LEA", loc - sym["val"])
            else:
                self.emitter.emit("IMM", sym["val"])
        elif left.node_name == "IndexExpr":
            self.expr(left, loc)  # 简化：下标按值处理
        else:
            self.expr(left, loc)

    def _lvalue_type(self, left: Node) -> int:
        if left.node_name == "Identifier":
            name = self._ident_text(left)
            sym = self.symbols.get(name)
            if sym:
                return sym["type"]
        return INT

    # ── 程序/函数 ──
    def compile_program(self, root: Node) -> _Emitter:
        self._first_pass(root)  # 声明收集（全局/函数名）
        for item in getattr(root, "sub_node", []) or []:
            name = item.node_name
            if name == "VarDecl":
                self._global_var(item)
            elif name == "FuncDef":
                self._function(item)
        self.emitter.resolve()
        return self.emitter

    def _first_pass(self, root: Node) -> None:
        """预扫描：注册全局变量/函数名（地址分配），字符串入池。"""
        for item in getattr(root, "sub_node", []) or []:
            if item.node_name == "VarDecl":
                for vn in self._decl_names(item):
                    self._declare(vn, GLO, INT, self._data_addr)
                    self._data_addr += 4
            elif item.node_name == "FuncDef":
                fname = self._ident_text(getattr(item, "name", None))
                self._declare(fname, FUN, INT, 0)

    def _decl_names(self, vd: Node) -> list[str]:
        names = []
        n1 = self._ident_text(getattr(vd, "name", None))
        if n1:
            names.append(n1)
        more = getattr(vd, "more", None)
        if more is not None:
            for c in more.iter_children():
                r = self._ident_text(c)
                if r:
                    names.append(r)
        return names

    def _global_var(self, vd: Node) -> None:
        names = self._decl_names(vd)
        if names:
            sym = self.symbols.get(names[0])
            if sym and sym["class"] == GLO:
                self.emitter.label(f"G{names[0]}")
        init = getattr(vd, "init", None)
        if init is not None:
            self.emitter.emit("IMM", self._int_value(init))
            self.emitter.emit("SI")

    def _function(self, fn: Node) -> None:
        fname = self._ident_text(getattr(fn, "name", None))
        self.emitter.label(f"F{fname}")
        # 参数
        i = 0
        params = getattr(fn, "params", None)
        param_nodes = self._param_list(params)
        for pn in param_nodes:
            pname = self._ident_text(getattr(pn, "name", None))
            self._declare(pname, LOC, INT, i)
            i += 1
        loc = i + 1  # 局部基址（c4: loc = ++i）
        # 局部声明（body 内 VarDecl）
        body = getattr(fn, "body", None)
        for c in getattr(body, "sub_node", []) or []:
            if c.node_name == "VarDecl":
                for vn in self._decl_names(c):
                    i += 1
                    self._declare(vn, LOC, INT, i)
        self.emitter.emit("ENT", i - loc)
        # 编译 body 语句（跳过局部声明）
        for c in getattr(body, "sub_node", []) or []:
            if c.node_name != "VarDecl":
                self.stmt(c, loc)
        self.emitter.emit("LEV")

    def _param_list(self, params: Node | None) -> list[Node]:
        if params is None:
            return []
        items = getattr(params, "items", None)
        if isinstance(items, list):
            return [it for it in items if isinstance(it, Node) and it.node_name == "ParamDecl"]
        ch = list(params.iter_children())
        return [c for c in ch if isinstance(c, Node) and c.node_name == "ParamDecl"]


@register_plugin
class AsmGenPlugin(TransformPlugin):
    """c4 → c4 VM 汇编生成插件。

    process 守卫：仅当根节点是 c4 的 Program（is_block 根块）时生成汇编；
    其它语言 AST 原样返回。
    """

    def __init__(self) -> None:
        self._stats = {"asm_lines": 0}

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def process(self, ast: Node, root_scope: Scope) -> Node:
        if ast is None or ast.node_name != "Program":
            return ast
        compiler = _C4Compiler()
        emitter = compiler.compile_program(ast)
        asm = Node("AsmProgram")
        for line in emitter.lines():
            ln = Node("AsmLine", text=line)
            asm.add_sub_node(ln)
        self._stats["asm_lines"] = len(compiler.emitter.code)
        return asm
