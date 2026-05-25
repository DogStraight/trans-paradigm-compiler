# parser/feature_analyze.py
from typing import Optional, Tuple, Dict, Any
import re

# 处理分支和序列的优先级顺序及对应的类型与字段名
SEPARATOR_HANDLERS = [
    ("|", "choice", "alternatives"),  # 分支优先级最高
    (",", "seq", "items"),  # 序列次之
]

# 后缀运算符映射
SUFFIX_MAP = {
    "+": "plus",
    "*": "repeat",
    "?": "optional",
}


def analyze_production_features(production: str) -> Optional[Dict[str, Any]]:
    """
    分析产生式字符串，返回纯字典结构的中间 AST。
    支持后缀操作符：
        *  零次或多次 -> {"type": "repeat", "elem": ...}
        +  一次或多次 -> {"type": "plus", "elem": ...}
        ?  零次或一次 -> {"type": "optional", "elem": ...}
    """
    placeholder_map: Dict[str, Optional[Dict[str, Any]]] = {}

    def find_outermost_paren(s: str) -> Optional[Tuple[int, int]]:
        stack = []
        for i, ch in enumerate(s):
            if ch == "(":
                stack.append(i)
            elif ch == ")" and stack:
                start = stack.pop()
                if not stack:
                    return (start, i)
        return None

    def build_tree(s: str) -> Optional[Dict[str, Any]]:
        s = s.strip().replace(" ", "")
        if not s:
            return None

        # 1. 括号占位
        paren = find_outermost_paren(s)
        if paren:
            start, end = paren
            before = s[:start]
            inner = s[start + 1 : end]
            after = s[end + 1 :]
            inner_ast = build_tree(inner)
            placeholder = f"__paren_{len(placeholder_map)}__"
            placeholder_map[placeholder] = inner_ast
            new_s = before + placeholder + after
            return build_tree(new_s)

        if s in placeholder_map:
            return placeholder_map[s]

        for sep, typ, field in SEPARATOR_HANDLERS:
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                return {
                    "type": typ,
                    field: [build_tree(p) for p in parts if build_tree(p) is not None],
                }

        # 3. 后缀运算符（优先级最高）：'+', '*', '?'
        for suffix, typ in SUFFIX_MAP.items():
            if s.endswith(suffix):
                base = s[:-1].strip()
                return {"type": typ, "elem": build_tree(base)}

        # 4. 语法调用 '@Rule'
        if (
            s.startswith("@")
            and len(s) > 1
            and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", s[1:])
        ):
            return {"type": "call", "name": s[1:]}

        # 5. 普通 token
        if re.match(r"^[a-zA-Z_\.]+$", s):
            return {"type": "token", "token_type": s}

        raise ValueError(f"无效的产生式片段: {s}")

    try:
        return build_tree(production)
    except Exception as e:
        raise Exception(f"分析产生式失败 {production}: {str(e)}")


if __name__ == "__main__":
    test_cases = [
        "id",
        "@Expression",
        "symbol.base.colon",
        "(@MulOp,@PrimaryExpr)*",
        "literal.number|literal.string",
        "(@VarDef|newline)*",
        "(id , symbol.base.colon , id , symbol.base.equal , @Expression)?",
        "id.keyword.if, @Expression, @Block",
        "id+",
        "(@Expr)+",
        "(id , symbol.base.colon , @Type)+",
        "literal+ | @FuncCall+",
        "(@Stmt|newline)*",
    ]
    for prod in test_cases:
        try:
            ast = analyze_production_features(prod)
            print(f"产生式: {prod}")
            print(f"AST: {ast}")
            print("-" * 60)
        except Exception as e:
            print(f"失败: {prod} -> {e}")
