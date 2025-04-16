from typing import Generator

from pyv_definition import Token
from pyv_utils import get_token_define
from pyv_err import IndentationError, UnexpectedTokenError


class PyvLexer:
    token_define: dict = {}

    def __init__(
        self,
        token_define_dict: dict = get_token_define("grammar/token.toml")
    ) -> None:
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

        # is output comments
        self.output_comments = False
        pass

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
            elif lex_text[text_idx] in self.bracket:
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
            elif lex_text[text_idx] in self.token_define["space"].values():
                space_content: str = ""
                start_point += 1  # move on
                while lex_text[text_idx] in \
                    self.token_define["space"].values() \
                        and text_idx + 1 <= lex_text_len:
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

            # in case current char is a symbol
            elif lex_text[text_idx] in\
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
            elif lex_text[text_idx] in \
                    self.token_define["comment"]["boundary"]:
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
                if self.output_comments:
                    yield current_token
                continue

            # in case current char is an id
            elif lex_text[text_idx].isalpha() or lex_text[text_idx] == "_":
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
            elif lex_text[text_idx].isdigit():
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
            elif lex_text[text_idx] == '"' or lex_text[text_idx] == "'":
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
            else:
                current_token.set_type("unrecognized")
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point+offset)

                # reset line info
                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                yield current_token
        pass

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
                else:
                    raise IndentationError(
                        f"Indentation error at: {_token.start.column}")
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
            case "unrecognized":
                raise UnexpectedTokenError(
                    f"Unexpected token: {_token.content} "
                    f"at: line: {_token.start.line}, "
                    f"column: {_token.start.column}")

            # case default
            case _:
                # do nothing
                ...
        self.previous_token_type = _token.type
        return _token
