# lexer/lexer_utils.py
import tomllib
from core.define import FileManager


def get_token_define(
    token_define: str = FileManager.token_define_file,
) -> dict:
    token_define = FileManager.read_file(token_define)
    token_define_dict: dict = tomllib.loads(token_define)
    return token_define_dict


# 如果使能这个装饰器，则将返回的当前的token值的类型做一次简化，
# 只保留最后一个字段，如 keyword.if -> if
def simplify_output(is_simplify: bool):
    def inner(func):
        def wrapper(*args, **kwargs):
            tokens: list = func(*args, **kwargs)
            for token in tokens:
                token.type = token.type.split(".")[-1] if is_simplify else token.type
            return tokens

        return wrapper

    return inner
