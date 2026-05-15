from define import Token


# ----- 辅助函数，用于判断 token 的分层类型 -----
def is_number(token: Token):
    """判断 token 是否为数字字面量"""
    return token.type == "literal.number"


def is_string(token: Token):
    """判断 token 是否为字符串字面量"""
    return token.type == "literal.string"


def is_bool(token: Token):
    """判断 token 是否为布尔字面量"""
    return token.type in ("literal.bool_true", "literal.bool_false")


def is_identifier(token: Token):
    """判断 token 是否为标识符（id.id 或 id.keyword.*）"""
    return token.type.startswith("id.")


def is_operator(token: Token):
    """判断 token 是否为运算符（symbol.base.* 或 symbol.extend.*）"""
    return token.type.startswith("symbol.base.") or token.type.startswith(
        "symbol.extend."
    )


def is_paren(token: Token):
    """判断 token 是否为括号（bracket.*）"""
    return token.type.startswith("bracket.")
