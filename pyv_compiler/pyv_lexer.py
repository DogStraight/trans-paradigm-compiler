
from toml import loads as toml_loads
from typing import Generator


class Token:

    class Position:
        def __init__(self):
            self.line = 0
            self.column = 0

    def __init__(self) -> None:
        self.content: str = ""
        self.type: str = ""
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


class Lexer:
    current_lex_file: str = ""
    token_define: dict = {}

    def __init__(self, token_define_dict: dict):
        self.indent_deep = 0
        self.indent_level = 4
        self.token_define = token_define_dict
        self.blank: list = \
            list(token_define_dict["space"].values()) \
            + list(token_define_dict["newline"].values())
        self.bracket: list = list(self.token_define["bracket"].values())
        self.newline: list = list(self.token_define["newline"].values())
        self.base_symbol: list = \
            list(self.token_define["symbol"]["base"].values())

        self.previous_token_type: str = ""

    def set_current_lex_file(self, file_name: str) -> None:
        self.current_lex_file = file_name

    # Generator[Token, None, None] no send method, no return value
    def tokenize(self, lex_text: str) -> Generator[Token, None, None]:
        lex_text_len: int = len(lex_text)
        lex_text = lex_text + "\n"  # add a newline at the end

        # token pos relative
        text_idx: int = 0
        line_number: int = 1
        start_point: int = 0

        # token container
        current_token: Token = Token()

        while text_idx < lex_text_len:
            # reset offset
            offset = 0

            # get next char
            next_char: str = ""
            if text_idx+1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

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
                current_token = self.refine_type(current_token)
                yield current_token
                continue

            # in case current char is a bracket
            if lex_text[text_idx] in self.bracket:
                # set current token line info
                current_token.set_type("bracket")
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                yield current_token
                continue

            # in case current char is a space
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
                current_token = self.refine_type(current_token)
                if current_token.type == "space":
                    continue
                yield current_token
                continue

            # in case current char is a symbol
            if lex_text[text_idx] in\
                    self.token_define["symbol"]["base"].values():
                extend_symbol = f"{lex_text[text_idx]}{next_char}"
                current_token.set_content(lex_text[text_idx])
                current_token.set_type("symbol.base")
                text_idx += 1
                offset += 1
                if extend_symbol in \
                        self.token_define["symbol"]["extend"].values():
                    current_token.set_content(extend_symbol)
                    current_token.set_type("symbol.extend")
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                yield current_token
                continue

            # in case current char in comment
            if lex_text[text_idx] in self.token_define["comment"]["boundary"]:
                comment_content: str = ""
                while lex_text[text_idx] != "\n":
                    comment_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                current_token.set_type("comment")
                current_token.set_content(comment_content)

                # set current token line info
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info\
                start_point += offset
                current_token = self.refine_type(current_token)
                yield current_token
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
                current_token = self.refine_type(current_token)
                yield current_token
                continue

            # in case current char is a number
            if lex_text[text_idx].isdigit():
                number_content: str = ""
                while lex_text[text_idx] not in self.blank\
                        and lex_text[text_idx] not in self.bracket\
                        and lex_text[text_idx] not in self.base_symbol:
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
                current_token = self.refine_type(current_token)
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
                current_token = self.refine_type(current_token)
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
            current_token = self.refine_type(current_token)
            yield current_token

    # only use in method tokenize
    def refine_type(self, _token: Token) -> Token:
        # this method provide more refined token type #
        match _token.type:
            # in case token type is space
            case "space":
                if self.previous_token_type != "newline":
                    _token.type = "space"
                elif len(_token.content) % self.indent_level == 0:
                    current_indent_deep: int = \
                        int(len(_token.content) / self.indent_level)
                    if current_indent_deep > self.indent_deep:
                        _token.type += "." + "indent"
                    elif current_indent_deep == self.indent_deep:
                        _token.type += "." + "indent_keep"
                    else:
                        _token.type += "." + "dedent"
                    self.indent_deep = current_indent_deep
            # in case token type is id
            case "id":
                id_kw_set = self.token_define[_token.type]["keyword"]
                if _token.content == id_kw_set["logic_add"] \
                        or _token.content == id_kw_set["logic_not"] \
                        or _token.content == id_kw_set["logic_or"]:
                    _token.type = "symbol.base" + ".logic_" + _token.content
                elif _token.content in id_kw_set:
                    _token.type = "keyword" + "." + _token.content
                else:
                    _token.type = "id"

                # in extra case literal
                if _token.content == "True" or _token.content == "False":
                    _token.type = "literal.bool_true" \
                        if _token.content == "True" else "literal.bool_false"

                if _token.content == "None":
                    _token.type = "literal.none"

            # in case token type is bracket
            case "bracket":
                for bracket_type in self.token_define["bracket"]:
                    if _token.content == \
                            self.token_define["bracket"][bracket_type]:
                        _token.type += "." + bracket_type
                        break

            # in case token type is symbol
            # base symbol
            case "symbol.base":
                for base_symbol in self.token_define["symbol"]["base"]:
                    if _token.content == \
                            self.token_define["symbol"]["base"][base_symbol]:
                        _token.type += "." + base_symbol
                        break
            # extend symbol
            case "symbol.extend":
                for ex_symbol in self.token_define["symbol"]["extend"]:
                    if _token.content == \
                            self.token_define["symbol"]["extend"][ex_symbol]:
                        _token.type += "." + ex_symbol
                        break

            # in case token type is unrecognized
            case _:
                # do not thing
                ...
        self.previous_token_type = _token.type
        return _token

    # gen original code from tokens
    @staticmethod
    def untokenize(token_generator: Generator[Token, None, None]) -> str:
        untokenize_string: str = ""
        for _token in token_generator:
            untokenize_string += _token.content
        return untokenize_string
    pass


def _lex_input(lexer: Lexer, input_str: str) -> Generator[Token, None, None]:
    # do not use this function, only for testing
    return lexer.tokenize(input_str)


def _read_token_define(token_define: str) -> dict:
    with open(token_define, 'r') as _f:
        token_define = _f.read()
    token_define_dict: dict = toml_loads(token_define)
    return token_define_dict


def _print_token_stream(token: Token, file=None):
    if token.content == "\n":
        token.content = "\\n"
    start_loc = f"{token.start.line}:{token.start.column}"
    end_loc = f"{token.end.line}:{token.end.column}"
    print(
        f"c: {token.content:<20}",  # just for good looking
        f"s: {start_loc:<8}",  # these number has no meaning
        f"e: {end_loc:<8}",
        f"t: {token.type}",
        file=file)


if __name__ == "__main__":

    # load token define from file
    token_define = _read_token_define("grammar/token.toml")

    # instance lexer
    pyv_lexer = Lexer(token_define)

    # instance argparse
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=str, nargs="?",
                        default="./grammar/module_define.pyv",
                        help='lexer file input')
    parser.add_argument('-o', '--output',
                        type=str, nargs="?", default="output/test.token",
                        help='lexer result output file path')
    parser_args = parser.parse_args()

    # load args
    lex_file = parser_args.file
    out_file = None
    if parser_args.output is not None:
        out_file = open(parser_args.output, "w")

    # load text
    if lex_file is None:
        exit(1)
    with open(f"{lex_file}") as f:
        lex_text = f.read()

    # output lexer result
    for token in pyv_lexer.tokenize(lex_text=lex_text):
        _print_token_stream(token, out_file)

    if out_file is not None:
        out_file.close()

    # print run done
    print(f"run done,output file: {parser_args.output}")
