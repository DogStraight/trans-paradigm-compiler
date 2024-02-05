# the purpose of this file is :
#   generate token flow from text file and finish type mark

import re
import pyv_config


class FileChecker:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        pass

    def has_trailing_newline(self):
        with open(self.filename, "r") as f:
            last_line = f.readlines()[-1]
            return last_line.endswith("\n")

    def fix_trailing_newline(self):
        if not self.has_trailing_newline():
            with open(self.filename, "a") as f:
                f.write("\n")


class CharIterator:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_point = open(self.file_path, "r")

    def __iter__(self):
        return self

    def __next__(self) -> str:
        char = self.file_point.read(1)
        if not char:
            self.file_point.close()
            raise StopIteration
        return char


class WordIterator:
    def __init__(self, char_iterator: CharIterator):
        self.char_iterator = char_iterator
        self.word = ""
        self.last_separator_char = ""

    def __iter__(self):
        return self

    def __next__(self) -> str:
        if self.last_separator_char:
            last_separator_char = self.last_separator_char
            self.last_separator_char = ""
            return last_separator_char
        char = next(self.char_iterator)
        if char in pyv_config.separator_char:
            return char
        while char not in pyv_config.separator_char:
            self.word += char
            char = next(self.char_iterator)
        self.last_separator_char = char
        word = self.word
        self.word = ""
        return word


class TokenTypeMarker:
    def __init__(self, word_iterator: WordIterator):
        self.word_iterator = word_iterator
        self.last_word = ""
        self.tail_word = ""
        self.indent_cnt = 0
        self.indent_deep = 0
        pass

    def __iter__(self):
        return self

    def __next__(self) -> tuple[str, pyv_config.TokenType]:
        if self.tail_word:
            word = self.tail_word
            self.tail_word = ""
        else:
            word = next(self.word_iterator)
        if word in pyv_config.blank_char_set:
            token_type = pyv_config.TokenType.BLANK
            if word == " " and self.last_word == "\n":
                self.last_word = word
                while word == " ":
                    word = next(self.word_iterator)
                    self.indent_cnt += 1
                if self.indent_cnt % pyv_config.indent_level == 0:
                    indent_size = self.indent_deep * pyv_config.indent_level
                    if self.indent_cnt >= indent_size:
                        token_type = pyv_config.TokenType.INDENT
                    elif self.indent_cnt < indent_size:
                        token_type = pyv_config.TokenType.REDUCE
                self.indent_cnt = 0
                if token_type == pyv_config.TokenType.INDENT:
                    self.indent_deep += 1
                elif token_type == pyv_config.TokenType.REDUCE:
                    self.indent_deep -= 1
                self.tail_word = word
                return ("", token_type)
        elif word in pyv_config.key_word_set:
            token_type = pyv_config.TokenType.KEY_WORD
        elif re.compile(pyv_config.id_regex).match(word):
            token_type = pyv_config.TokenType.IDENTIFIER
        elif word in pyv_config.operator_set:
            token_type = pyv_config.TokenType.OPERATOR
        elif word in pyv_config.operator_set:
            token_type = pyv_config.TokenType.OPERATOR
        else:
            token_type = pyv_config.TokenType.UNDEFINED
        self.last_word = word
        return (word, token_type)


class pyvLexer:
    def __init__(self) -> None:
        self.lex_result: list[tuple[str, pyv_config.TokenType]] = []

    def lex(self, file: str):
        file_checker = FileChecker(file)
        file_checker.fix_trailing_newline()
        char_iterator = CharIterator(file)
        word_iterator = WordIterator(char_iterator)
        raw_token_iter = TokenTypeMarker(word_iterator)
        for token in raw_token_iter:
            self.lex_result.append(token)
        return self.lex_result


if __name__ == "__main__":
    lexer = pyvLexer()
    lex_result = lexer.lex("./tests/some_token_example.txt")
    print(lex_result)
