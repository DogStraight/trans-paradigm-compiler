"""Lexer — tokenizer driven by _token.toml configuration.

Converts Verilog source text into a stream of Token objects.
Keyword/symbol/literal/comment/whitespace patterns are all defined
in TOML — no hardcoded lexer logic.

配置通过 ConfigRegistry 声明式加载。
"""

from core.define import Token
from core.config_registry import config

from .lexer_utils import get_token_define_merged
from .number_fsm import NumberFSM
from .comment_fsm import CommentFSM


class Lexer:
    token_define: dict = {}

    def __init__(
        self,
        token_define_dict: dict | None = None,
        rules_dir: str | None = None,
        ext_dirs: list[str] | None = None,
    ) -> None:
        if rules_dir:
            token_define_dict = get_token_define_merged(rules_dir, ext_dirs)
        else:
            from .lexer_utils import get_token_define

            token_define_dict = get_token_define()
        self.token_define = token_define_dict

        # 宏识别策略与配置
        # 分 directive（指令关键字）和 call（宏调用）两段，每段独立配置 strategy 和参数
        self._macro_dir_cfg: dict = {}  # directive 段配置
        self._macro_call_cfg: dict = {}  # call 段配置
        self.macro_config = {}
        try:
            raw = config.get("lexer.macro_config")
            if raw:
                rec = raw.get("macro_recognition", {})
                self._macro_dir_cfg = rec.get("directive", {})
                self._macro_call_cfg = rec.get("call", {})
                self.macro_config = {d: f"macro.{d}" for d in raw.get("directives", {})}
        except KeyError:
            pass

        self.indent_enable = token_define_dict.get("indent", {}).get("enable", False)
        self.indent_level = token_define_dict.get("indent", {}).get("level", 4)
        self.indent_deep = 0
        self.blank: list = list(token_define_dict.get("space", {}).values()) + list(
            token_define_dict.get("newline", {}).values()
        )
        self.newline: list = list(token_define_dict.get("newline", {}).values())
        self.alpha_tokens = []
        self._build_alpha_tokens()
        self.full_token_map: dict[str, str] = self._build_full_token_map()

        # 括号配对表 → 开闭集合 + 类型映射
        bracket_pairs: list = self.token_define.get("bracket", {}).get("pairs", [])
        self.open_brackets: set[str] = set()
        self.close_brackets: set[str] = set()
        self.bracket_type_map: dict[str, str] = {}
        for open_c, close_c, name in bracket_pairs:
            self.open_brackets.add(open_c)
            self.close_brackets.add(close_c)
            self.bracket_type_map[open_c] = f"bracket.l_{name}"
            self.bracket_type_map[close_c] = f"bracket.r_{name}"
        self.bracket_depth: int = 0

        self.previous_token_type: str = ""

        # new line start flag for indent handling
        self.new_line_start = False
        pass

    def _build_alpha_tokens(self) -> None:
        """构建字母形式 token 映射列表 (value, type)"""
        self.alpha_tokens.clear()

        # 1. symbol.base 和 symbol.extend
        for cat in ("base", "extend"):
            for sym_name, sym_value in (
                self.token_define.get("symbol", {}).get(cat, {}).items()
            ):
                if isinstance(sym_value, str) and sym_value.isalpha():
                    self.alpha_tokens.append((sym_value, f"symbol.{cat}.{sym_name}"))

        # 2. bracket（来自 pairs 结构）
        for open_c, close_c, name in self.token_define.get("bracket", {}).get(
            "pairs", []
        ):
            if isinstance(open_c, str) and open_c.isalpha():
                self.alpha_tokens.append((open_c, f"bracket.l_{name}"))
            if isinstance(close_c, str) and close_c.isalpha():
                self.alpha_tokens.append((close_c, f"bracket.r_{name}"))

        # 3. literal 精确字面量（排除 string, number）
        for lit_name, lit_value in self.token_define.get("literal", {}).items():
            if lit_name in ("string", "number"):
                continue
            if isinstance(lit_value, str) and lit_value.isalpha():
                self.alpha_tokens.append((lit_value, f"literal.{lit_name}"))

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
            current_token: Token = Token(line=line_number, column=start_point)

            # reset offset
            offset = 0

            # get next char
            next_char: str = ""
            if text_idx + 1 < lex_text_len:
                next_char = lex_text[text_idx + 1]

            # in case current char is a newline char
            if lex_text[text_idx] in self.newline:
                start_point += 1

                current_token.set_type("newline")
                current_token.set_content(lex_text[text_idx])

                line_number += 1
                text_idx += 1
                start_point = 0
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                self.new_line_start = True
                continue

            # in case current char is a space
            elif lex_text[text_idx] in self.token_define["space"].values():
                space_content: str = ""
                while (
                    text_idx < lex_text_len
                    and lex_text[text_idx] in self.token_define["space"].values()
                ):
                    space_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                # handle indentation only when this line just started
                if self.new_line_start and self.indent_enable:
                    # empty line (only spaces followed by newline) -> ignore
                    if text_idx < lex_text_len and lex_text[text_idx] in self.newline:
                        self.new_line_start = True
                    else:
                        # 行首空格：先判 bracket 深度，再用能否整除判断折行
                        if self.bracket_depth > 0:
                            # 括号内：抑制一切结构缩进（仅用于对齐，非结构变化）
                            current_depth = self.indent_deep
                        elif len(space_content) % self.indent_level != 0:
                            # 不对齐 → 续行折行，保持当前深度
                            current_depth = self.indent_deep
                        else:
                            # 对齐到缩进网格 → 结构深度变化
                            current_depth = len(space_content) // self.indent_level

                        if current_depth > self.indent_deep:
                            # 结构缩进
                            while self.indent_deep < current_depth:
                                indent_token = Token(
                                    line=line_number, column=start_point
                                )
                                indent_token.set_type("space.indent")
                                indent_token.set_content(space_content)
                                tokens.append(indent_token)
                                self.indent_deep += 1
                        elif current_depth < self.indent_deep:
                            # 结构反缩进
                            while self.indent_deep > current_depth:
                                dedent_token = Token(
                                    line=line_number, column=start_point
                                )
                                dedent_token.set_type("space.dedent")
                                dedent_token.set_content("")
                                tokens.append(dedent_token)
                                self.indent_deep -= 1
                        else:  # current_depth == self.indent_deep
                            # 同深度：不对齐且括号外才是折行
                            if (
                                self.bracket_depth == 0
                                and len(space_content) % self.indent_level != 0
                            ):
                                fold_token = Token(line=line_number, column=start_point)
                                fold_token.set_type("space.fold")
                                fold_token.set_content("")
                                tokens.append(fold_token)

                        self.new_line_start = False
                # else: ignore

                # update start_point
                start_point += len(space_content)
                continue

            # comment — 使用 CommentFSM 解析（完全配置驱动）
            elif any(
                lex_text[text_idx : text_idx + len(s)] in (s,)
                for s in CommentFSM.get_start_patterns(self.token_define)
            ):
                result = CommentFSM.run(lex_text, text_idx, self.token_define)
                if result is not None:
                    comment_content, new_idx, kind = result
                    self._emit_pending_dedent(tokens)
                    current_token.set_type("comment")
                    current_token.set_content(comment_content)
                    current_token = self.refine_type(current_token)
                    tokens.append(current_token)
                    offset = new_idx - text_idx
                    text_idx = new_idx
                    start_point += offset
                    # comments at beginning of line should not affect indentation
                    if self.new_line_start:
                        self.new_line_start = False
                    continue

            # in case current char is unsized Verilog literal ('b1, 'd0, 'hFF, 'o7)
            elif lex_text[text_idx] == "'" and next_char in "dDbBhHoO":
                self._emit_pending_dedent(tokens)

                number_content, new_idx = NumberFSM.run(lex_text, text_idx)
                offset = new_idx - text_idx

                current_token.set_type("literal.number")
                current_token.set_content(number_content)

                text_idx = new_idx
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is a symbol
            elif lex_text[text_idx] in self.token_define["symbol"]["base"].values():
                # handle possible dedent before actual token
                self._emit_pending_dedent(tokens)

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

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is a bracket
            elif (
                lex_text[text_idx] in self.open_brackets
                or lex_text[text_idx] in self.close_brackets
            ):
                self._emit_pending_dedent(tokens)

                # 跟踪括号深度
                if lex_text[text_idx] in self.open_brackets:
                    self.bracket_depth += 1
                else:
                    self.bracket_depth -= 1

                current_token.set_type("bracket")
                current_token.set_content(lex_text[text_idx])

                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # (comment handled by CommentFSM in earlier branch)

            # in case current char is an id
            elif lex_text[text_idx].isalpha() or lex_text[text_idx] == "_":
                self._emit_pending_dedent(tokens)

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

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # ── 宏 token 识别（prefix 策略）──
            #
            # 按 directive → call 顺序检查，相同前缀时 directive 优先。
            # 命中 directives 表 → macro.<key>；未命中且 call 策略相同 → macro.call。
            #
            dir_prefix = (
                self._macro_dir_cfg.get("prefix", "")
                if self._macro_dir_cfg.get("strategy") == "prefix"
                else ""
            )
            call_prefix = (
                self._macro_call_cfg.get("prefix", "")
                if self._macro_call_cfg.get("strategy") == "prefix"
                else ""
            )
            ch = lex_text[text_idx]
            matched_prefix = ""
            check_dir = False
            if dir_prefix and ch == dir_prefix:
                matched_prefix = dir_prefix
                check_dir = True
            elif call_prefix and ch == call_prefix:
                matched_prefix = call_prefix

            if matched_prefix:
                self._emit_pending_dedent(tokens)
                macro_content = ch
                text_idx += 1
                while text_idx < lex_text_len and (
                    lex_text[text_idx].isalpha()
                    or lex_text[text_idx] == "_"
                    or lex_text[text_idx].isdigit()
                ):
                    macro_content += lex_text[text_idx]
                    text_idx += 1
                    offset += 1

                macro_name = macro_content[1:]  # 去掉前缀
                macro_type = (
                    self.macro_config.get(macro_name, "macro.call")
                    if check_dir
                    else "macro.call"
                )
                current_token.set_type(macro_type)
                current_token.set_content(macro_content)

                start_point += len(macro_content)
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is a number

            # in case current char is a number
            elif lex_text[text_idx].isdigit():
                self._emit_pending_dedent(tokens)

                number_content, new_idx = NumberFSM.run(lex_text, text_idx)
                offset = new_idx - text_idx

                # set current token line info
                current_token.set_type("literal.number")
                current_token.set_content(number_content)

                # reset line info
                text_idx = new_idx
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char is in string
            elif lex_text[text_idx] == '"' or lex_text[text_idx] == "'":
                self._emit_pending_dedent(tokens)

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

                # reset line info
                start_point += offset
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
                continue

            # in case current char has nowhere to put
            else:
                self._emit_pending_dedent(tokens)

                current_token.set_type("unrecognized")
                current_token.set_content(lex_text[text_idx])

                # reset line info
                text_idx += 1
                start_point += 1
                current_token = self.refine_type(current_token)
                tokens.append(current_token)
        return tokens

    def _emit_pending_dedent(self, tokens: list[Token]) -> None:
        """当新行没有前导空格时，输出所有待处理的 dedent 令牌"""
        if self.new_line_start:
            while self.indent_deep > 0:
                dedent_token = Token(line=0, column=0)
                dedent_token.set_type("space.dedent")
                dedent_token.set_content("")
                tokens.append(dedent_token)
                self.indent_deep -= 1
            self.new_line_start = False

    def _build_full_token_map(self) -> dict[str, str]:
        """构建 {原始字符串: 完整类型名} 的扁平映射表"""
        m: dict[str, str] = {}
        # bracket（来自 pairs）
        for open_c, close_c, name in self.token_define.get("bracket", {}).get(
            "pairs", []
        ):
            m[open_c] = f"bracket.l_{name}"
            m[close_c] = f"bracket.r_{name}"
        # symbol.base
        for name, val in self.token_define.get("symbol", {}).get("base", {}).items():
            if isinstance(val, str):
                m[val] = f"symbol.base.{name}"
        # symbol.extend
        for name, val in self.token_define.get("symbol", {}).get("extend", {}).items():
            if isinstance(val, str):
                m[val] = f"symbol.extend.{name}"
        # literal 精确匹配（排除 string/number 等由 lexer 正则处理的）
        for name, val in self.token_define.get("literal", {}).items():
            if name in ("string", "number"):
                continue
            if isinstance(val, str):
                m[val] = f"literal.{name}"
        # keyword（从 token_define["id"]["keyword"] 加载）
        for kw, orig in self.token_define.get("id", {}).get("keyword", {}).items():
            if isinstance(orig, str):
                m[orig] = f"keyword.{orig}"
        return m

    # only use in method tokenize
    def refine_type(self, _token: Token) -> Token:
        # this method provide more refined token type #
        if _token.type == "unrecognized":
            raise ValueError(f"Unexpected token: {_token.content} ")
        if _token.type == "id":
            # 扁平映射表查找：覆盖 keyword / bracket / symbol 等字母形式
            full_type = self.full_token_map.get(_token.content)
            if full_type is not None:
                _token.type = full_type
            else:
                _token.type = "id"
        elif _token.type in ("bracket", "symbol.base", "symbol.extend"):
            full_type = self.full_token_map.get(_token.content)
            if full_type is not None:
                _token.type = full_type
        # else: 保持原有类型（newline / space / literal.string / literal.number / comment 等）
        self.previous_token_type = _token.type
        return _token
