"""
registry.py — 预处理器指令处理器注册中心

与 renderer/primitives/registry.py / analyzer/primitives/registry.py 对称设计。
每个子系统都在 primitives/registry.py 中定义注册表 + @register 装饰器。
Doc: preprocessor/README.md
"""

from typing import Any, Callable

# ── Handler 签名 ──────────────────────────────────
# context 是 handler 之间共享的运行时状态
DirectiveContext = dict[str, Any]
DirectiveHandler = Callable[[str, str, str, DirectiveContext], None]


def split_directive(stripped: str, prefix: str) -> tuple[str, str]:
    """指令行 → (关键字, 关键字之后的文本)。

    切分规则 = **前缀 + 关键字 + 空白 + 参数**：关键字 = 前缀后第一段非空白，
    其后文本（已去前导空白）就是 handler 的参数。关键字**拼写**来自语言包的
    候选名声明（`[macro_recognition] directive`）——本函数不写死任何关键字，
    分隔空白也不假定为单个空格（TAB 等同样成立）。

    调用方：`scan_directives` 取关键字做分派，各 handler 取参数。
    """
    rest = stripped[len(prefix) :].lstrip()
    i = 0
    while i < len(rest) and not rest[i].isspace():
        i += 1
    return rest[:i], rest[i:].lstrip()


# ── 注册表 ────────────────────────────────────────

_registry: dict[str, tuple[DirectiveHandler, str]] = {}


def register_primitive(name: str, fn: DirectiveHandler, kind: str = "normal") -> None:
    """显式注册一个指令处理器。kind: "normal" | "control"。

    control 类指令（ifdef/else/endif 等）负责条件栈状态，无论当前分支是否
    活跃都必须执行；normal 类指令仅在活跃分支内执行。
    """
    _registry[name] = (fn, kind)


def get_primitive(name: str) -> DirectiveHandler | None:
    entry = _registry.get(name)
    return entry[0] if entry else None


def get_primitive_kind(name: str) -> str:
    entry = _registry.get(name)
    return entry[1] if entry else "normal"


def list_primitives() -> list[str]:
    return list(_registry.keys())


# ── 装饰器 ────────────────────────────────────────


def register(name: str, kind: str = "normal") -> Callable[[DirectiveHandler], DirectiveHandler]:
    """装饰器：注册一个指令处理器。

    Usage:
        @register("define")
        def handle_define(stripped, prefix, name, ctx):
            ...
    """

    def decorator(func: DirectiveHandler) -> DirectiveHandler:
        register_primitive(name, func, kind)
        return func

    return decorator
