from define import Token


# ========== 辅助函数：判断 token 类型 ==========
def is_number(token: Token) -> bool:
    return token.type == "literal.number"


def is_string(token: Token) -> bool:
    return token.type == "literal.string"


def is_bool(token: Token) -> bool:
    return token.type in ("literal.bool_true", "literal.bool_false")


def is_identifier(token: Token) -> bool:
    return token.type == "id" or token.type.startswith("id.")


def is_operator(token: Token) -> bool:
    return token.type.startswith("symbol.base.") or token.type.startswith(
        "symbol.extend."
    )


def is_paren(token: Token) -> bool:
    return token.type.startswith("bracket.")
