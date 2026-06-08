# lexer/main_lexer.py
from define import Token
from err import IndentationError, UnexpectedTokenError
from .lexer_utils import get_token_define, simplify_output


class Lexer:
    token_define: dict = {}

    def __init__(self, token_define_dict: dict = get_token_define()) -> None:
        self.indent_deep = 0
        self.indent_level = 4
        self.token_define = token_define_dict
        self.blank: list = list(token_define_dict["space"].values()) + list(
            token_define_dict["newline"].values()
        )
        self.bracket: list = list(self.token_define["bracket"].values())
        self.newline: list = list(self.token_define["newline"].values())
        self.base_symbol: list = list(self.token_define["symbol"]["base"].values())

        self.alpha_tokens = []
        self._build_alpha_tokens()

        # special case for number,
        self.base_symbol.remove(".")
        self.previous_token_type: str = ""

        # is output comments
        self.output_comments = False

        # new line start flag for indent handling
        self.new_line_start = False
        pass

    def _build_alpha_tokens(self) -> None:
        """构建字母形式 token 映射列表 (value, type)"""
        self.alpha_tokens.clear()

        # 1. symbol.base 和 symbol.extend
        for cat in ("base", "extend"):
            for sym_name, sym_value in self.token_define["symbol"][cat].items():
                if isinstance(sym_value, str) and sym_value.isalpha():
                    self.alpha_tokens.append((sym_value, f"symbol.{cat}.{sym_name}"))

        # 2. bracket
        for bracket_name, bracket_value in self.token_define["bracket"].items():
            if isinstance(bracket_value, str) and bracket_value.isalpha():
                self.alpha_tokens.append((bracket_value, f"bracket.{bracket_name}"))

        # 3. literal 精确字面量（排除 string, number）
        for lit_name, lit_value in self.token_define.get("literal", {}).items():
            if lit_name in ("string", "number"):
                continue
            if isinstance(lit_value, str) and lit_value.isalpha():
                self.alpha_tokens.append((lit_value, f"literal.{lit_name}"))

    @simplify_output(False)
    def tokenize(self, lex_text: str) -> list[Token]:
        lex_text_len: int = len(lex_text)
        lex_text = lex_text + "\n"  # add a newline at the end

        # token pos relative
        text_idx: int = 0
        line_number: int = 1
        start_point: int = 0

        # tokens
        tokens = []

        while text_idx < lex_text_len:
            # token container
            current_token: Token = Token()

            # reset offset
            offset = 0

            # get next char
            next_char: str = ""
            if text_idx + 1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

            # in case current char is a newline char
            if lex_text[text_idx] in self.newline:
                start_point += 1  # move on

                # set current token line info
                current_token.set_type("newline")
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                line_number += 1
                text_idx += 1
                start_point = 0
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                # mark new line start for next line
                self.new_line_start = True
                continue

            # in case current char is a space
            elif lex_text[text_idx] in self.token_define["space"].values():
                space_content: str = ""
                start_col = start_point
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] in self.token_define["space"].values()
                ):
                    space_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # handle indentation only when this line just started
                if self.new_line_start:
                    # empty line (only spaces followed by newline) -> ignore
                    if text_idx < lex_text_len and lex_text[text_idx] in self.newline:
                        # ignore spaces on empty line, do not change indent
                        self.new_line_start = True  # keep flag for next line
                    else:
                        # calculate indent depth
                        if len(space_content) % self.indent_level == 0:
                            current_depth = len(space_content) // self.indent_level
                        else:
                            raise IndentationError(
                                f"Indentation error at line {line_number}, column {start_col}"
                            )

                        if current_depth > self.indent_deep:
                            # emit indent token
                            indent_token = Token()
                            indent_token.set_type("space.indent")
                            indent_token.set_content(space_content)
                            indent_token.set_location(
                                line_number,
                                start_col,
                                line_number,
                                start_col + len(space_content),
                            )
                            tokens.append(indent_token)
                        elif current_depth < self.indent_deep:
                            # emit one or more dedent tokens
                            while self.indent_deep > current_depth:
                                dedent_token = Token()
                                dedent_token.set_type("space.dedent")
                                dedent_token.set_content("")
                                dedent_token.set_location(
                                    line_number, start_col, line_number, start_col
                                )
                                tokens.append(dedent_token)
                                self.indent_deep -= 1
                        # if equal: nothing to emit
                        self.indent_deep = current_depth
                        self.new_line_start = False
                # else: spaces inside a line -> ignore

                # update start_point
                start_point += len(space_content)
                continue

            # in case current chars is // comment (Verilog style)
            elif (
                lex_text[text_idx] == "/"
                and next_char == "/"
            ):
                self._emit_pending_dedent(tokens, line_number, start_point)
                if self.new_line_start:
                    self.new_line_start = False
                comment_content: str = ""
                while text_idx < lex_text_len and lex_text[text_idx] != "\n":
                    comment_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1
                current_token.set_type("comment")
                current_token.set_content(comment_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                start_point += offset
                continue

            # in case current char is a symbol
            elif lex_text[text_idx] in self.token_define["symbol"]["base"].values():
                # handle possible dedent before actual token
                self._emit_pending_dedent(tokens, line_number, start_point)

                extend_symbol = f"{lex_text[text_idx]}{next_char}"
                current_token.set_content(lex_text[text_idx])
                current_token.set_type("symbol.base")
                text_idx += 1
                offset += 1
                if extend_symbol in self.token_define["symbol"]["extend"].values():
                    current_token.set_content(extend_symbol)
                    current_token.set_type("symbol.extend")
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is a bracket
            elif lex_text[text_idx] in self.bracket:
                self._emit_pending_dedent(tokens, line_number, start_point)

                # set current token line info
                current_token.set_type("bracket")
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char in comment
            elif lex_text[text_idx] in self.token_define["comment"]["boundary"]:
                # comments at beginning of line should not affect indentation
                if self.new_line_start:
                    # ignore indent for comment-only line
                    self.new_line_start = False

                comment_content: str = ""
                while text_idx < lex_text_len and lex_text[text_idx] != "\n":
                    comment_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                current_token.set_type("comment")
                current_token.set_content(comment_content)

                # set current token line info
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info\
                start_point += offset
                current_token = self.refine_type(current_token)
                if self.output_comments:
                    tokens.append(current_token)
                continue

            # in case current char is an id
            elif lex_text[text_idx].isalpha() or lex_text[text_idx] == "_":
                self._emit_pending_dedent(tokens, line_number, start_point)

                id_content: str = lex_text[text_idx]
                text_idx += 1
                while text_idx < lex_text_len and (
                    lex_text[text_idx].isalpha()
                    or lex_text[text_idx] == "_"
                    or lex_text[text_idx].isdigit()
                ):
                    id_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_type("id")
                current_token.set_content(id_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is a number
            elif lex_text[text_idx].isdigit():
                self._emit_pending_dedent(tokens, line_number, start_point)

                number_content: str = ""
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] not in self.blank
                    and lex_text[text_idx] not in self.bracket
                    and lex_text[text_idx] not in self.base_symbol
                ):
                    number_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # set current token line info
                current_token.set_type("literal.number")
                current_token.set_content(number_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is in string
            elif lex_text[text_idx] == '"' or lex_text[text_idx] == "'":
                self._emit_pending_dedent(tokens, line_number, start_point)

                end_char: str = lex_text[text_idx]
                string_content: str = ""
                string_content += lex_text[text_idx]
                text_idx += 1
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] != end_char
                    and lex_text[text_idx] != "\n"
                ):
                    string_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1
                if text_idx < lex_text_len:
                    string_content += lex_text[text_idx]
                    text_idx += 1

                # set current token line info
                current_token.set_type("literal.string")
                current_token.set_content(string_content)
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char has nowhere to put
            else:
                self._emit_pending_dedent(tokens, line_number, start_point)

                current_token.set_type("unrecognized")
                current_token.set_content(lex_text[text_idx])
                current_token.set_location(
                    line_number, start_point, line_number, start_point + offset
                )

                # reset line info
                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
        return tokens

    def _emit_pending_dedent(self, tokens: list[Token], line: int, column: int) -> None:
        """当新行没有前导空格时，输出所有待处理的 dedent 令牌"""
        if self.new_line_start:
            while self.indent_deep > 0:
                dedent_token = Token()
                dedent_token.set_type("space.dedent")
                dedent_token.set_content("")
                dedent_token.set_location(line, column, line, column)
                tokens.append(dedent_token)
                self.indent_deep -= 1
            self.new_line_start = False

    # only use in method tokenize
    def refine_type(self, _token: Token) -> Token:
        # this method provide more refined token type #
        match _token.type:
            # space indentation is already handled in tokenize loop
            case "space":
                # should not reach here normally, but keep for safety
                _token.type = "space"

            # in case token type is id
            case "id":
                # 1. 尝试匹配字母形式的 token（符号、括号、精确字面量）
                matched = False
                for value, typ in self.alpha_tokens:
                    if _token.content == value:
                        _token.type = typ
                        matched = True
                        break

                if not matched:
                    # 2. 原有关键字检查
                    id_kw_set = self.token_define[_token.type]["keyword"]
                    if _token.content in id_kw_set:
                        _token.type = "keyword." + _token.content
                    else:
                        _token.type = "id"

            # in case token type is bracket
            case "bracket":
                for bracket_type in self.token_define["bracket"]:
                    if _token.content == self.token_define["bracket"][bracket_type]:
                        _token.type += "." + bracket_type
                        break

            # in case token type is symbol
            # base symbol
            case "symbol.base":
                for base_symbol in self.token_define["symbol"]["base"]:
                    if (
                        _token.content
                        == self.token_define["symbol"]["base"][base_symbol]
                    ):
                        _token.type += "." + base_symbol
                        break
            # extend symbol
            case "symbol.extend":
                for ex_symbol in self.token_define["symbol"]["extend"]:
                    if (
                        _token.content
                        == self.token_define["symbol"]["extend"][ex_symbol]
                    ):
                        _token.type += "." + ex_symbol
                        break

            # in case token type is unrecognized
            case "unrecognized":
                raise UnexpectedTokenError(
                    f"Unexpected token: {_token.content} "
                    f"at: line: {_token.start.line}, "
                    f"column: {_token.start.column}"
                )

            # case default
            case _:
                # do nothing
                ...
        self.previous_token_type = _token.type
        return _token
