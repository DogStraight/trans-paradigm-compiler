from typing import Generator
import re
import copy

from .pyv_lexer import Token, Lexer
from .pyv_ast_node import \
    Node, RootNode, ClassDefNode, PortListNode, \
    TagNode, \
    InterfaceNode, ExpressionNode, AttributeNode, CallableNode, \
    IfNode
from .pyv_utils import testing_function, unfinished_function, \
    get_op_precedence, get_close_bracket_string, \
    get_builtin_types
from .pyv_err import ParsingError


class Parser:
    ####################################
    # init method
    ####################################
    def __init__(self, token_input: Generator) -> None:
        self.token_input: Generator = token_input
        self.ast: RootNode = RootNode()
        self.node_level: list[Node] = [self.ast]
        self.current_node: Node = self.ast

        # peek flag
        self.has_peeked: bool = False
        self.peek_token = None
        self.current_token = None
        pass

    ####################################
    # alias for self operation
    ####################################

    def _node_level_step_down(self) -> None:
        self.node_level.pop()
        self.current_node = self.node_level[-1]

    def _node_level_step_up(self, node) -> None:
        self.current_node.add_node(node)
        self.node_level.append(node)
        self.current_node = node

    ####################################
    # parser state machine related method
    ####################################

    def advance(self) -> Token:
        if self.has_peeked:
            self.has_peeked = False
            self.current_token = self.peek_token
            return self.current_token
        self.current_token = next(self.token_input)
        return self.current_token

    def peek(self) -> Token:
        if not self.has_peeked:
            self.has_peeked = True
            return next(self.token_input)
        return self.current_token

    def consume(self, token: Token) -> None:
        if "keyword" in token.type:
            parse_method = getattr(self, f"_parse_{token.content}")
            parse_method()
        elif "id" in token.type:
            pass
        elif "newline" in token.type:
            if self.peek().type != "indent" \
                    and self.node_level[-1] != self.ast:
                print("Should have indent after newline")
        elif "dedent" in token.type:
            self._node_level_step_down()
        else:
            self.advance()
        pass

    ####################################
    # expression related method
    ####################################

    @testing_function
    def _parse_numeric_expression(self, target_string: str) -> ExpressionNode:
        lexer = Lexer()
        tokens = []

        # 初始化tokens
        for token in lexer.tokenize(target_string):
            token_copy = copy.deepcopy(token)
            tokens.append(token_copy)
        tokens_copy = []
        combine_flag = False

        # 合并attribute
        for token, idx in zip(tokens, range(len(tokens))):
            if "dot" in token.type:
                node = AttributeNode()
                if idx > 0 and (isinstance(tokens[idx-1], Token) or
                                isinstance(tokens[idx-1], AttributeNode)):
                    node.add_name(tokens_copy.pop())  # pop name
                else:
                    raise ParsingError(f"Invalid attribute: {token.content}")
                if idx < len(tokens)-1:
                    print(f"missing attribute for {tokens[idx-1].content}")
                node.add_attr(tokens[idx+1].content)
                tokens_copy.append(node)
                combine_flag = True
                continue
            elif combine_flag is True:
                combine_flag = False
                continue
            else:
                tokens_copy.append(token)
                continue
        tokens = tokens_copy
        tokens_copy = []
        combine_flag = False

        # 处理调用
        for token, idx in zip(tokens, range(len(tokens))):
            if "l_parentheses" in token.type and idx > 0:
                assert (isinstance(tokens[idx-1], Token) or
                        isinstance(tokens[idx-1], AttributeNode))
                node = CallableNode()
                node.add_name(tokens_copy.pop())  # pop name
                # 提取括号内的字符串
                extract_string: str = get_close_bracket_string(
                    token.content,
                    target_string[idx:])
                node.add_arguments(extract_string.strip("()"))
                tokens_copy.append(node)
                combine_flag = True
                compare_string = ""
            elif combine_flag is True:
                compare_string += token.content
                if compare_string in extract_string:
                    continue
                else:
                    tokens_copy.append(token)
                    combine_flag = False
            else:
                tokens_copy.append(token)
        tokens = tokens_copy
        tokens_copy = []

        # 合并括号表达式
        str_idx = 0
        compare_string: str = ""
        for token in tokens:
            if "l_parentheses" in token.type:
                node = ExpressionNode()
                node.set_type("parentheses")
                # 提取括号内的字符串
                extract_string: str = get_close_bracket_string(
                    token.content,
                    target_string[str_idx:])
                node.add_right_operand(
                    self._parse_expression(extract_string.strip("()")))
                tokens_copy.append(node)
                str_idx += len(extract_string)
                combine_flag = True
                compare_string = ""
            elif combine_flag is True:
                compare_string += token.content
                if compare_string in extract_string:
                    continue
                else:
                    tokens_copy.append(token)
                    combine_flag = False
            else:
                tokens_copy.append(token)
        tokens = tokens_copy
        tokens_copy = []

        # 找到所有单边的操作符,并合并操作数
        for token, idx in zip(tokens, range(len(tokens))):
            if "symbol" not in token.type:
                tokens_copy.append(token)
            elif combine_flag is True:
                # 合并操作符
                continue
            elif "symbol" in token.type:
                # 找到单边操作符
                if token.content in ["!", "&", "|", "^", "~", "-"]:
                    # 单边操作符在开头或前一个操作符为单边操作符
                    if idx == 0 or "symbol" in tokens[idx-1].type:
                        node = ExpressionNode()
                        node.set_type("unary")
                        node.set_operator(token.content)
                        node.add_right_operand(tokens[idx+1])
                        tokens_copy.append(node)
                        combine_flag = True
                else:
                    tokens_copy.append(token)
        tokens = tokens_copy
        tokens_copy = []
        combine_flag = False

        # 合成表达式
        op_precedence = get_op_precedence()
        max_precedence = 0
        max_iteration_depth = 20
        combine_flag = False
        while len(tokens) > 1 and max_iteration_depth > 0:
            for token, idx in zip(tokens, range(len(tokens))):
                # 获取优先级最高的操作符
                for _ in range(len(tokens)):
                    if "symbol" in tokens[_].type:
                        max_precedence = max(
                            op_precedence[tokens[_].type.split(".")[-1]],
                            max_precedence)
                # 处理操作符
                if "symbol" in token.type \
                        and op_precedence[
                            token.type.split(".")[-1]] == max_precedence:
                    node = ExpressionNode()
                    node.set_type("numeric")
                    node.add_operator(token)
                    node.add_left_operand(tokens_copy.pop())
                    if idx < len(tokens)-1:
                        raise ParsingError(
                            f"missing right operand for {token.content}")
                    node.add_right_operand(tokens[idx+1])
                    tokens_copy.append(node)
                    combine_flag = True
                    continue
                elif combine_flag is True:
                    combine_flag = False
                    continue
                else:
                    tokens_copy.append(token)
            tokens = tokens_copy
            tokens_copy = []
            max_precedence = 0
            max_iteration_depth -= 1
            if max_iteration_depth > 0:
                print("expression is too complex")
        return tokens[0]

    @unfinished_function
    def _parse_bool_expression(self, target_string: str) -> ExpressionNode:
        pass

    def _parse_expression(self, target_string: str) -> ExpressionNode:
        numeric_pattern = re.compile(r'^[A-Za-z0-9\'\s\+\-\*/\.()]+$')
        if numeric_pattern.match(target_string):
            node = self._parse_numeric_expression(target_string)
        else:
            node = self._parse_bool_expression(target_string)
        return node

    ####################################
    # keyword related method
    ####################################

    def _check_token_type(self, token: Token, token_type: str) -> bool:
        if token_type in token.type:
            return True
        print("expect token type: ", token_type, "but got: ", token.type)
        return False

    def _parse_class(self) -> None:
        node = ClassDefNode()
        self._node_level_step_up(node)
        class_name_token = self.advance()

        # update class name
        if not self._check_token_type(class_name_token, "id"):
            raise Exception(f"Invalid class name: {class_name_token.content}")
        node.set_class_name(class_name_token.content)

        # check bases
        if self._check_token_type(self.peek(), "l_parentheses"):
            self.advance()
            while True:
                if self._check_token_type(self.peek(), "comma"):
                    continue
                base_name_token = self.advance()
                if not self._check_token_type(base_name_token, "id"):
                    raise Exception(
                        f"Invalid base class name: {base_name_token.content}")
                node.add_base_class(base_name_token.content)
                if self._check_token_type(self.peek(), "r_parentheses"):
                    break

        # colon
        if self._check_token_type(self.advance(), "colon"):
            raise Exception(
                f"Invalid class body: {self.current_token.content}")
        pass

    # port list
    def _parse_input(self) -> None:
        node = PortListNode(list_type="input")
        self._node_level_step_up(node)
        self._check_token_type(self.advance(), "colon")  # consume ":"
        self._check_token_type(self.advance(), "newline")  # consume "newline"
        self._check_token_type(self.advance(), "indent")  # consume "indent"
        while True:
            # handle port name
            port_name_token = self.advance()
            if not self._check_token_type(port_name_token, "id"):
                raise Exception(
                    f"Invalid port name: {port_name_token.content}")
            node.add_port(port_name_token.content)

            # handle type
            # check if there is colon
            peek = self.peek()
            if self._check_token_type(peek, "colon"):
                self.advance()  # consume ":"
                # check if there is type
                peek = self.peek()
                if self._check_token_type(peek, "id"):
                    build_in_type = get_builtin_types()
                    if peek.content in build_in_type:
                        node.add_port_type(peek.content)
                        self.advance()  # consume type
                        self.advance()  # consume "newline"
            # no colon, should be a type
            elif self._check_token_type(peek, "newline"):
                node.add_port_type("bit")
                self.advance()  # consume "newline"

            # skip newline and indent_keep
            while self._check_token_type(self.peek(), "newline") \
                    or self._check_token_type(self.peek(), "indent_keep"):
                self.advance()  # consume "newline" or "indent_keep"
            # if dedent is found node update is done
            if self._check_token_type(self.peek(), "dedent"):
                break
        self.advance()  # consume "dedent"
        pass

    @unfinished_function
    def _parse_output(self) -> None:
        node = PortListNode(list_type="output")
        self._node_level_step_up(node)
        self._check_token_type(self.advance(), "colon")  # consume ":"
        self._check_token_type(self.advance(), "newline")  # consume "newline"
        self._check_token_type(self.advance(), "indent")  # consume "indent"
        while True:
            # handle port name
            port_name_token = self.advance()
            if not self._check_token_type(port_name_token, "id"):
                raise Exception(
                    f"Invalid port name: {port_name_token.content}")
            node.add_port(port_name_token.content)

            # handle type
            # check if there is colon
            peek = self.peek()
            if self._check_token_type(peek, "colon"):
                self.advance()  # consume ":"
                # check if there is type
                peek = self.peek()
                if self._check_token_type(peek, "id"):
                    build_in_type = get_builtin_types()
                    if peek.content in build_in_type:
                        node.add_port_type(peek.content)
                        self.advance()  # consume type
                        self.advance()  # consume "newline"
            # no colon, should be a type
            elif self._check_token_type(peek, "newline"):
                node.add_port_type("bit")
                self.advance()  # consume "newline"

            # handle port default value
            if self._check_token_type(self.peek(), "equal"):
                self.advance()  # consume "="
                while self._check_token_type(self.peek(), "newline"):
                    default_value_string += self.advance().content

                self.advance()  # consume "newline"

            # skip newline and indent_keep
            while self._check_token_type(self.peek(), "newline") \
                    or self._check_token_type(self.peek(), "indent_keep"):
                self.advance()  # consume "newline" or "indent_keep"
            # if dedent is found node update is done
            if self._check_token_type(self.peek(), "dedent"):
                break
        self.advance()  # consume "dedent"
        pass

        pass

    @unfinished_function
    def _parse_inout(self) -> None:
        pass

    @unfinished_function
    def _parse_if(self) -> None:
        node = IfNode()
        self._node_level_step_up(node)

    ####################################
    # main method for parser
    ####################################

    def parse(self, token_input: Generator[Token, None, None]) -> None:
        for token in token_input:
            self.consume(token)
        pass

    def dump_ast(self) -> dict:
        return self.ast.dump()
