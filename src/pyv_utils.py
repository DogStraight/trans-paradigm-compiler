from pathlib import Path

from toml import loads as toml_loads
from pyv_err import BracketMismatchError
from pyv_definition import GrammarRule


####################################
# file read
####################################
def get_token_define(
    token_define: str = str(Path(__file__).parent.parent / "grammar" / "token.toml"),
) -> dict:
    with open(token_define, "r") as _f:
        token_define = _f.read()
    token_define_dict: dict = toml_loads(token_define)
    return token_define_dict


####################################
# string manipulation
####################################
def get_close_bracket_string(start_bracket: str, target_string: str) -> str:
    close_bracket = ""
    close_bracket_dict = {"(": ")", "[": "]", "{": "}", "<": ">"}
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
    return extract_string[1:-1]


class RecursionGuardManager:
    def __init__(self):
        self.call_stack = {}

    def guard(self, max_depth):
        def wrapper(func):
            def inner(*args, **kwargs):
                func_name = func.__name__
                self.call_stack[func_name] = self.call_stack.get(func_name, 0) + 1

                if self.call_stack[func_name] > max_depth:
                    raise RecursionError(
                        f"Max recursion depth {max_depth} exceeded in function '{func_name}'\n"
                        f"Current call stack: {self.call_stack}"
                    )

                try:
                    return func(*args, **kwargs)
                finally:
                    self.call_stack[func_name] -= 1
                    if self.call_stack[func_name] == 0:
                        del self.call_stack[func_name]

            return inner

        return wrapper


def load_rule(name, rule_content) -> GrammarRule:
    return GrammarRule(
        name=name,
        production=rule_content["production"],
        node=rule_content["node"],
    )
