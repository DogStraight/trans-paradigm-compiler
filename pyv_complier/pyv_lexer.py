from abc import abstractmethod, ABC
from os import get_terminal_size
from toml import loads as toml_loads

from pyv_decorator import override


class Token:

    class Position:
        def __init__(self):
            self.line = 0
            self.column = 0

    def __init__(self) -> None:
        self.content = ""
        self.type = 0
        self.start: Token.Position = Token.Position()
        self.end: Token.Position = Token.Position()

    def set_content(self, content: str) -> None:
        self.content = content

    def set_location(
        self,
        start_line: int,
        start_colum: int,
        end_line: int,
        end_colum: int
    ) -> None:
        self.start.line = start_line
        self.start.column = start_colum
        self.end.line = end_line
        self.end.column = end_colum

    def set_type(self, token_type: int) -> None:
        self.type = token_type


class Tokenizer(ABC):
    @abstractmethod
    def tokenize(self) -> None:
        pass


class TokenTypeMarker(ABC):
    @abstractmethod
    def mark_type(self) -> None:
        pass


class Lexer(Tokenizer, TokenTypeMarker):
    current_lex_file: str = ""
    token_define: dict = {}

    def __init__(self, token_define: dict):
        self.token_define = token_define
        self.blank: list = \
            list(token_define["space"].values()) \
            + list(token_define["newline"].values())
        self.bracket: list = list(self.token_define["bracket"].values())
        self.newline: list = list(self.token_define["newline"].values())

    def set_current_lex_file(self, file_name: str) -> None:
        self.current_lex_file = file_name

    @override
    def tokenize(self, lex_text: str):
        lex_text_len: int = len(lex_text)
        text_idx: int = 0
        line_number: int = 0
        start_point: int = 0
        offset: int = 0
        current_token: Token = Token()
        while text_idx < lex_text_len:
            # reset offset
            offset = 0

            # get next char
            next_char: str = ""
            if text_idx+1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

            # in case current char is an compiler instruction
            if lex_text[text_idx] in "#":
                while lex_text[text_idx] not in self.newline:
                    text_idx += 1
                line_number += 1
                continue

            # in case current char is a blank char
            if lex_text[text_idx] in self.newline:
                start_point += 1  # move on
                # set current token line info
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)
                # reset line info
                line_number += 1
                text_idx += 1
                start_point = 0
                yield current_token
                continue

            # in case current char is an bracket
            if lex_text[text_idx] in self.bracket:
                # set current token line info
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)
                # reset line info
                text_idx += 1
                start_point += 1
                yield current_token
                continue

            # in case current char is an space
            if lex_text[text_idx] in self.token_define["space"].values():
                start_point += 1  # move on
                while lex_text[text_idx] in \
                    self.token_define["space"].values() \
                        and text_idx + 1 < lex_text_len:
                    text_idx += 1
                    offset += 1
                offset -= 1  # expect current char

                # set current token line info
                current_token.set_content(" ")
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char is an operator
            if lex_text[text_idx] \
                    in self.token_define["operator"]["base"].values():
                extend_op = f"{lex_text[text_idx]}{next_char}"
                current_token.set_content(lex_text[text_idx])
                text_idx += 1
                offset += 1
                if extend_op in \
                        self.token_define["operator"]["extend"].values():
                    print(extend_op)
                    current_token.set_content(extend_op)
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)
                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char in comment
            # line comment
            if f"{lex_text[text_idx]}{next_char}" in "//":
                while lex_text[text_idx] != "\n":
                    text_idx += 1

                # reset line info
                start_point = 1
                continue

            # block comment
            if f"{lex_text[text_idx]}{next_char}" in "/*":
                while f"{lex_text[text_idx]}{next_char}" not in "*/" \
                        and text_idx + 1 < lex_text_len:
                    if lex_text[text_idx] in "\n":
                        line_number += 1
                        start_point = 1
                    text_idx += 1
                    start_point += 1
                    next_char = lex_text[text_idx + 1]
                start_point += 2  # out of block comment end
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
                    offset += 1

                # set current token line info
                current_token.set_content(id_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char is an number
            if lex_text[text_idx].isdigit():
                number_content: str = ""
                while lex_text[text_idx] not in self.blank\
                        and lex_text[text_idx] not in self.bracket:
                    number_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_content(number_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char is in string
            # "" string
            if lex_text[text_idx] == '"':
                string_content: str = ""
                string_content += lex_text[text_idx]
                text_idx += 1
                while lex_text[text_idx] != '"' and lex_text[text_idx] != "\n":
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                string_content += lex_text[text_idx]
                text_idx += 1

                # set current token line info
                current_token.set_content(string_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # '' string
            if lex_text[text_idx] == "'":
                string_content: str = ""
                string_content += lex_text[text_idx]
                text_idx += 1
                while lex_text[text_idx] != "'" and lex_text[text_idx] != "\n":
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                string_content += lex_text[text_idx]
                text_idx += 1

                # set current token line info
                current_token.set_content(string_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char has nowhere to put
            current_token.set_content(lex_text[text_idx])
            current_token.set_location(
                line_number, start_point, line_number, start_point+offset)

            # reset line info
            text_idx += 1
            start_point += 1
            yield current_token

    @override
    def mark_type(self, tokenized_list: list) -> list:
        pass


def read_token_define(token_define_toml_file_path: str) -> dict:
    with open(token_define_toml_file_path, 'r') as f:
        token_define = f.read()
    token_define_dict: dict = toml_loads(token_define)
    return token_define_dict


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
        if len(token.content) > max_token_len:
            max_token_len = len(token.content)
        if token.content == "\n":
            token.content = "\\n"
        print(
            f"c: {token.content:<20}",
            f"s: {token.start.line}:{token.start.column:<5}",
            f"e: {token.end.line}:{token.end.column}",
            file=log_file)
    log_file.close()
    print(f"max_token_len : {max_token_len}")
    print('",' in token_define["operator"]["extend"].values())
