# preprocessor/primitives/ — 预处理器指令处理器原语
#
# 每个指令一个文件，通过 @register("name") 自动注册。
# 新增指令只需新建文件 + 装饰器注册。

from . import define, undef, include

__all__ = ["define", "undef", "include"]