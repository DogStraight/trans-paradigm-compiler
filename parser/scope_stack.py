"""ScopeStack — 轻量作用域栈，供 Parser 在解析过程中实时查询符号。

与 Analyzer 的后阶段全量分析不同，ScopeStack 只服务于 Parser 的规则选择，
在回溯时需配合 snapshot/restore 回滚。

scope 声明来源：规则 TOML 中的 [RuleName.analyzer] scope = { ... }，
通过 peek 机制声明式复制到 parser 域。
"""

from typing import Optional
from core.define import GrammarRule


class ScopeEntry:
    """作用域条目"""

    def __init__(self, name: str, kind: str):
        self.name: str = name
        self.kind: str = kind
        # 本作用域中注册的符号
        self.symbols: dict[str, str] = {}


class ScopeStack:
    """轻量级作用域栈"""

    def __init__(self) -> None:
        # 根作用域（全局）
        self._stack: list[ScopeEntry] = [ScopeEntry("__global__", "global")]

    # ── 快照/恢复（配合 parser 回溯） ──

    def snapshot(self) -> int:
        """返回当前栈深度作为快照。"""
        return len(self._stack)

    def restore(self, depth: int) -> None:
        """恢复到指定栈深度（丢弃上层作用域）。"""
        while len(self._stack) > depth:
            self._stack.pop()

    # ── 作用域管理 ──

    def push(self, name: str, kind: str) -> None:
        """进入新作用域。"""
        self._stack.append(ScopeEntry(name, kind))

    def pop(self) -> None:
        """退出当前作用域。"""
        if len(self._stack) > 1:
            self._stack.pop()

    # ── 符号注册与查找 ──

    def register(self, name: str, kind: str) -> None:
        """在当前作用域注册符号。"""
        self._stack[-1].symbols[name] = kind

    def lookup(self, name: str) -> Optional[str]:
        """沿作用域链查找符号，返回其 kind，未找到返回 None。"""
        for entry in reversed(self._stack):
            if name in entry.symbols:
                return entry.symbols[name]
        return None

    # ── 查询 ──

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def current(self) -> ScopeEntry:
        return self._stack[-1]

    def current_kind(self) -> str:
        return self._stack[-1].kind

    def dump(self) -> list[dict]:
        """调试用：导出整个栈。"""
        return [
            {"name": e.name, "kind": e.kind, "symbols": dict(e.symbols)}
            for e in self._stack
        ]
