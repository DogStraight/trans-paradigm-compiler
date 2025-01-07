# this is and extra function base on lexer
from .pyv_lexer import Lexer, _read_token_define
from os import path


def pyv_format(file_path: str) -> None:
    if not path.isfile(file_path):
        print(f"{file_path} not a file")
        return None

    with open(file=file_path, mode="r")as f:
        file_content: str = f.read()

    # instance lexer
    token_define: dict = _read_token_define("grammar/token.toml")
    lexer = Lexer(token_define)

    # format
    format_content: str = lexer.untokenize(lexer.tokenize(file_content))

    with open(file=file_path, mode="w")as f:
        f.write(format_content)
    pass


if __name__ == "__main__":
    pyv_format("./grammar/module_define.pyv")
