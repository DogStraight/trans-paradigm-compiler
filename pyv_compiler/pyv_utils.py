import toml
from os import walk
from toml import loads as toml_loads

from pyv_err import BracketMismatchError


####################################
# decorators
####################################
def unfinished_function(func):
    def wrapper(*args, **kwargs):
        print(f"Function {func.__name__} is not finished yet.")
        return None
    return wrapper


def testing_function(func):
    def wrapper(*args, **kwargs):
        print(f"Testing function {func.__name__}...")
        result = func(*args, **kwargs)
        print(f"Test result: {result}")
        return result
    return wrapper


####################################
# file read
####################################
def get_op_precedence() -> dict:
    with open("./grammar/operator_precedence.toml", "r") as _f:
        file_content = _f.read()
    return toml.loads(file_content)


def get_builtin_types() -> list[str]:
    _, types, _ = next(walk("./grammar/type"))
    return types


def get_type_info(type_name: str) -> dict:
    with open(f"./grammar/type/{type_name}/type_{type_name}_info.toml", "r")\
            as _f:
        file_content = _f.read()
    return toml.loads(file_content)


def get_token_define(token_define: str) -> dict:
    with open(token_define, 'r') as _f:
        token_define = _f.read()
    token_define_dict: dict = toml_loads(token_define)
    return token_define_dict


####################################
# string manipulation
####################################
def get_close_bracket_string(
        start_bracket: str,
        target_string: str) -> str:
    close_bracket = ""
    close_bracket_dict = {
        "(": ")",
        "[": "]",
        "{": "}",
        "<": ">"
    }
    # check if start_bracket is valid
    if start_bracket not in close_bracket_dict:
        raise BracketMismatchError(f"Invalid start bracket: {start_bracket}")

    close_bracket = close_bracket_dict[start_bracket]
    start: bool = False
    l_bracket_cnt: int = 0
    r_bracket_cnt: int = 0
    extract_string: str = ""
    for ch in target_string:
        if ch == start_bracket:
            start = True
            l_bracket_cnt += 1
        elif ch == close_bracket:
            r_bracket_cnt += 1
        if start is True:
            extract_string += ch
        if start is True and l_bracket_cnt == r_bracket_cnt:
            break
    if l_bracket_cnt != r_bracket_cnt:
        raise BracketMismatchError(f"Invalid bracket pair in {target_string}")
    return extract_string
