"""engine.py — 格式化 pass 编排引擎

接收从 boundary 扫描得到的行上下文序列，按配置驱动依次执行 pass。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .boundary import LineContext


PassFn = Callable[[list[str], list[LineContext]], list[str]]


@dataclass
class FormatterPass:
    name: str
    enabled: bool = True
    kind: str = "category"
    handler: PassFn | None = None
    category_cfg: dict | None = None


class FormatterEngine:
    def __init__(self, passes: list[FormatterPass] | None = None):
        self._passes: list[FormatterPass] = passes or []

    def register(self, p: FormatterPass) -> None:
        self._passes.append(p)

    def run(self, lines: list[str], contexts: list[LineContext]) -> list[str]:
        result = list(lines)
        for p in self._passes:
            if not p.enabled:
                continue
            if p.kind == "handler" and p.handler:
                result = p.handler(result, contexts)
            elif p.kind == "category" and p.category_cfg:
                result = _run_category_pass(result, contexts, p.category_cfg)
        return result


def _run_category_pass(lines, contexts, cfg):
    from .passes.column_align import run_category_pass as _run
    return _run(lines, contexts, cfg)
