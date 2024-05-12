from abc import abstractmethod, ABCMeta
from pyv_decorator import override
import toml


def read_token_define(token_define_toml_file_path: str) \
        -> dict[str, dict[str, str]]:
    with open(token_define_toml_file_path, 'r') as f:
        token_define = f.read()
    token_define_dict: dict[str, dict[str, str]] = toml.loads(token_define)
    return token_define_dict


def read_src_file_text(src_file_path: str) -> str:
    with open(src_file_path, 'r') as f:
        file_text: str = f.read()
    return file_text


class Tokenizer(metaclass=ABCMeta):
    @abstractmethod
    def lex(self) -> None:
        pass


class TokenTypeMarker(metaclass=ABCMeta):
    @abstractmethod
    def mark_type(self) -> None:
        pass


class PyvLexer(Tokenizer, TokenTypeMarker):
    token_define: dict[str, dict[str, str]] = {}

    def __init__(self, token_define: dict[str, dict[str, str]]):
        self.token_define = token_define
        pass

    @override
    def lex(self, lex_text: str) -> list:
        lex_text_len: int = len(lex_text)
        text_idx: int = 0
        token_list: list[str] = []
        while text_idx < lex_text_len:
            # get next char
            next_char: str = lex_text[text_idx + 1]\
                if text_idx+1 < lex_text_len else " "

            # in case current char is a blank char
            if lex_text[text_idx] in self.token_define["newline"].values():
                text_idx += 1
                token_list.append("\n")
                continue

            if lex_text[text_idx] in self.token_define["space"].values():
                while lex_text[text_idx] in \
                        self.token_define["space"].values():
                    text_idx += 1
                token_list.append(" ")
                continue

            # in case current char is an operator
            if lex_text[text_idx] \
                    in self.token_define["operator"]["base"].values():
                extend_op = f"{lex_text[text_idx]}{next_char}"
                if extend_op in self.token_define["operator"]["extend"]:
                    token_list.append(extend_op)
                    text_idx += 2
                    continue
                token_list.append(lex_text[text_idx])
                text_idx += 1
                continue
            pass
        
            # if

    @override
    def mark_type(self) -> None:
        print(f"self at : {self.mark_type}")
        pass


if __name__ == "__main__":
    token_define = read_token_define(
        token_define_toml_file_path="grammar/token.toml")
    import json
    print(json.dumps(token_define, indent=4))
    # lex_file_text = read_src_file_text(
    #     src_file_path="./pyv_complier/pyv_lexer.py")

    # pyv_trans_lexer = PyvLexer(token_define=token_define)
    # pyv_trans_lexer.lex()
    # pyv_trans_lexer.mark_type()
    pass
