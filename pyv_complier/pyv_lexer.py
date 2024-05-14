from abc import abstractmethod, ABC
from os import get_terminal_size
from toml import loads as toml_loads

from pyv_decorator import override


def read_token_define(token_define_toml_file_path: str) \
        -> dict:
    with open(token_define_toml_file_path, 'r') as f:
        token_define = f.read()
    token_define_dict: dict = toml_loads(token_define)
    return token_define_dict


class Tokenizer(ABC):
    @abstractmethod
    def tokenize(self) -> None:
        pass


class TokenTypeMarker(ABC):
    @abstractmethod
    def mark_type(self) -> None:
        pass


class Token:
    class Position:
        line: int
        column: int

    content: str
    type: int
    line_number: int
    start_position: tuple[Position]
    end_position: tuple[Position]


class Lexer(Tokenizer, TokenTypeMarker):
    current_lex_file: str = ""
    token_define: dict = {}

    def __init__(self, token_define: dict[str, dict[str, str]]):
        self.token_define = token_define
        self.blank: set = \
            set(list(token_define["space"].values()) +
                list(token_define["newline"].values()))
        self.bracket = set(self.token_define["bracket"].values())
        self.newline = set(self.token_define["newline"].values())

    @override
    def tokenize(self, lex_text: str) -> list:
        lex_text_len: int = len(lex_text)
        text_idx: int = 0
        line_number: int = 0
        token_list: list[str] = []
        while text_idx < lex_text_len:
            # get next char
            next_char: str = ""
            if text_idx+1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

            # in case current char is an compiler instruction
            if lex_text[text_idx] in "#":
                while lex_text[text_idx] not in self.newline:
                    text_idx += 1
                continue

            # in case current char is a blank char
            if lex_text[text_idx] in self.newline:
                line_number += 1
                text_idx += 1
                token_list.append("\n")
                continue

            # in case current char is an bracket
            if lex_text[text_idx] in self.bracket:
                token_list.append(lex_text[text_idx])
                text_idx += 1
                continue

            # in case current char is an space
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
                if extend_op in \
                        self.token_define["operator"]["extend"].values():
                    token_list.append(extend_op)
                    text_idx += 2
                    continue
                token_list.append(lex_text[text_idx])
                text_idx += 1
                continue

            # in case current char in comment
            # line comment
            if f"{lex_text[text_idx]}{next_char}" in "//":
                line_comment_content: str = ""
                while lex_text[text_idx] != "\n":
                    line_comment_content += lex_text[text_idx]
                    text_idx += 1
                token_list.append(line_comment_content)
                continue

            # block comment
            if f"{lex_text[text_idx]}{next_char}" in "/*":
                block_comment_content: str = ""
                while f"{lex_text[text_idx]}{next_char}" not in "*/" \
                        and text_idx + 1 < lex_text_len:
                    block_comment_content += lex_text[text_idx]
                    text_idx += 1
                    next_char = lex_text[text_idx + 1]
                if block_comment_content[-2:-1] not in "*/":
                    block_comment_content += "*/"
                token_list.append(block_comment_content)
                continue

            # in case current char is an id
            if lex_text[text_idx].isalpha() or lex_text[text_idx] == "_":
                id_content: str = lex_text[text_idx]
                text_idx += 1
                while lex_text[text_idx].isalpha() \
                        or lex_text[text_idx] == "_"\
                        or lex_text[text_idx].isdigit():
                    id_content += lex_text[text_idx]
                    text_idx += 1
                token_list.append(id_content)
                continue

            # in case current char is an number
            if lex_text[text_idx].isdigit():
                number_content: str = ""
                while lex_text[text_idx] not in self.blank\
                        and lex_text[text_idx] not in self.bracket:
                    number_content += lex_text[text_idx]
                    text_idx += 1
                token_list.append(number_content)
                continue

            # in case current char is in string
            if lex_text[text_idx] == "\"":
                string_content: str = ""
                while lex_text[text_idx] != "\"" or lex_text[text_idx] != "\n":
                    string_content += lex_text[text_idx]
                    text_idx += 1
                token_list.append(string_content)
                continue

            # in case current char has nowhere to put
            token_list.append(lex_text[text_idx])
            text_idx += 1
        return token_list

    @override
    def mark_type(self, tokenized_list: list) -> list:
        print(tokenized_list.clear)
        print(f"self at : {self.mark_type}")


if __name__ == "__main__":

    # load token define from file
    token_define = read_token_define(
        token_define_toml_file_path="grammar/token.toml")

    # instance lexer
    pyv_lexer = Lexer(token_define)

    # load text
    with open(f"{__file__}") as f:
        lex_text = f.read()

    # with open("./test/test_syntax.pyv") as f:
    #     lex_text = f.read()

    terminal_columns = get_terminal_size().columns
    token_number = 0
    log_file = open("./test.token", "w")
    max_token_len = 0
    for token in pyv_lexer.tokenize(lex_text=lex_text):
        if len(token) > max_token_len:
            max_token_len = len(token)
        if token == "\n":
            token = "\\n"
        print(
            f"token : '{token}'"
            f"{token_number:>{terminal_columns-len(token)-60}}",
            file=log_file)
        token_number += 1
    print(f"max token len : {max_token_len}")
    log_file.close()
