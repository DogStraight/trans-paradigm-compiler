from abc import abstractmethod, ABC
from toml import loads as toml_loads


class Token:

    class Position:
        def __init__(self):
            self.line = 0
            self.column = 0

    def __init__(self) -> None:
        self.content = ""
        self.type = ""
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

    def set_type(self, token_type: str) -> None:
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
        self.indent_deep = 0
        self.indent_level = 4
        self.token_define = token_define
        self.blank: list = \
            list(token_define["space"].values()) \
            + list(token_define["newline"].values())
        self.bracket: list = list(self.token_define["bracket"].values())
        self.newline: list = list(self.token_define["newline"].values())

    def set_current_lex_file(self, file_name: str) -> None:
        self.current_lex_file = file_name

    def tokenize(self, lex_text: str):
        lex_text_len: int = len(lex_text)

        # token pos relative
        text_idx: int = 0
        line_number: int = 1
        start_point: int = 0
        offset: int = 0

        # token container
        current_token: Token = Token()

        while text_idx < lex_text_len:
            # reset offset
            offset = 0

            # get next char
            next_char: str = ""
            if text_idx+1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

            # in case current char is an compiler instruction
            if lex_text[text_idx] in \
                    self.token_define["compiler"]["_preambles"]:
                while lex_text[text_idx] not in self.newline:
                    text_idx += 1
                line_number += 1
                continue

            # in case current char is a newline char
            if lex_text[text_idx] in self.newline:
                start_point += 1  # move on

                # set current token line info
                current_token.set_type("newline")
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
                current_token.set_type("bracket")
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
                space_content: str = ""
                start_point += 1  # move on
                while lex_text[text_idx] in \
                    self.token_define["space"].values() \
                        and text_idx + 1 < lex_text_len:
                    space_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_type("space")
                current_token.set_content(space_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char is an op
            if lex_text[text_idx] \
                    in self.token_define["op"]["base"].values():
                extend_op = f"{lex_text[text_idx]}{next_char}"
                current_token.set_content(lex_text[text_idx])
                current_token.set_type("op.base")
                text_idx += 1
                offset += 1
                if extend_op in \
                        self.token_define["op"]["extend"].values():
                    current_token.set_content(extend_op)
                    current_token.set_type("op.extend")
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
                    start_point += 1
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
                current_token.set_type("id")
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
                current_token.set_type("literal.number")
                current_token.set_content(number_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char is in string
            if lex_text[text_idx] == '"' or lex_text[text_idx] == "'":
                end_char: str = lex_text[text_idx]
                string_content: str = ""
                string_content += lex_text[text_idx]
                text_idx += 1
                while lex_text[text_idx] != end_char \
                        and lex_text[text_idx] != "\n":
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1
                string_content += lex_text[text_idx]
                text_idx += 1

                # set current token line info
                current_token.set_type("literal.string")
                current_token.set_content(string_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                yield current_token
                continue

            # in case current char has nowhere to put
            current_token.set_type("unrecognized")
            current_token.set_content(lex_text[text_idx])
            current_token.set_location(
                line_number, start_point, line_number, start_point+offset)

            # reset line info
            text_idx += 1
            start_point += 1
            yield current_token

    def mark_type(self, token: Token) -> Token:
        match token.type:
            # in case token type is space
            case "space":
                if len(token.content) % self.indent_level == 0:
                    current_indent_deep = \
                        len(token.content) / self.indent_level
                    if current_indent_deep >= self.indent_deep:
                        token.type += "." + "indent"
                    else:
                        token.type += "." + "dedent"
                    self.indent_deep = current_indent_deep
            # in case token type is id
            case "id":
                if token.content in self.token_define[token.type]["keyword"]:
                    token.type += "." + "keyword" + "." + token.content
                else:
                    token.type += "." + "identifier"

                # in extra case literal
                if token.content == "True" or token.content == "False":
                    token.type = "literal.bool_true" \
                        if token.content == "True" else "literal.bool_false"

            # in case token type is bracket
            case "bracket":
                for bracket_type in self.token_define["bracket"]:
                    if token.content == \
                            self.token_define["bracket"][bracket_type]:
                        token.type += "." + bracket_type
                        break

            # in case token type is op
            # base op
            case "op.base":
                for base_op_type in self.token_define["op"]["base"]:
                    if token.content == \
                            self.token_define["op"]["base"][base_op_type]:
                        token.type += "." + base_op_type
                        break
            # extend op
            case "op.extend":
                for extend_op_type in self.token_define["op"]["extend"]:
                    if token.content == \
                            self.token_define["op"]["extend"][extend_op_type]:
                        token.type += "." + extend_op_type
                        break
        return token


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

    # instance argparse
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=str, nargs=1,
                        help='lexer file input')
    parser_args = parser.parse_args()
    # load text
    with open(f"{parser_args.file[0]}") as f:
        lex_text = f.read()
    if len(lex_text) == 0:
        print("file empty")

    log_file = open("./test.token", "w")
    for token in pyv_lexer.tokenize(lex_text=lex_text):
        token = pyv_lexer.mark_type(token)
        if token.content == "\n":
            token.content = "\\n"
        print(
            f"c: {token.content:<20}",
            f"s: {token.start.line}:{token.start.column:<5}",
            f"e: {token.end.line}:{token.end.column:<5}",
            f"t: {token.type}",
            file=log_file)
    log_file.close()
