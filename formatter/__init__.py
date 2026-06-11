# formatter/__init__.py
from .verilog_formatter import VerilogFormatter as Formatter


def format_code(code: str) -> str:
    """
    对生成的代码进行缩进和块合并格式化。

    :param code:  原始代码字符串
    :return:      格式化后的代码字符串
    """

    fmt = Formatter()
    return fmt.format(code)


__all__ = ["Formatter", "format_code"]
