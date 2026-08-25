"""engine.py — 格式化 pass 编排引擎

接收从 boundary 扫描得到的行上下文序列，按配置驱动依次执行 pass。

Doc: docs/decisions/0006-renderer-improve-roadmap.md（改进路线：阶段 3 世界 B 升级目标）
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

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
        ctxs = list(contexts)
        for p in self._passes:
            if not p.enabled:
                continue
            if p.kind == "handler" and p.handler:
                result = p.handler(result, ctxs)
            elif p.kind == "category" and p.category_cfg:
                result = _run_category_pass(result, ctxs, p.category_cfg)
            # 带结构行兜底（ADR-0006 阶段 3）：pass 拆行改变行数但漏同步
            # contexts（如未来新增的 handler pass）时，按就近行派生补齐，
            # 杜绝"行号漂移"（后续 pass 按 index 取 contexts 不再错位）。
            ctxs = _resync_contexts(result, ctxs)
        return result


def _resync_contexts(
    lines: list[str], contexts: list[LineContext]
) -> list[LineContext]:
    """contexts 与 lines 对齐兜底：变长部分按最近 ctx 派生复制。

    拆行 pass（inst_port/wrap）已自行同步 contexts（就地更新），此函数只
    覆盖"漏同步"的防御：result 比 contexts 多出的行，复制最近一个 ctx
    （拆出的行属同一结构上下文）。contexts 比 lines 多则截断。
    """
    if len(contexts) >= len(lines):
        return contexts[: len(lines)]
    out = list(contexts)
    last = out[-1] if out else None
    for _ in range(len(lines) - len(contexts)):
        if last is None:
            out.append(LineContext(line_number=len(out) + 1, text=""))
            continue
        out.append(replace(last))
    return out


def _run_category_pass(lines, contexts, cfg):
    from .passes.column_align import run_category_pass as _run
    return _run(lines, contexts, cfg)
