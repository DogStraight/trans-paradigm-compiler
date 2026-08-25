"""engine.py — 格式化 pass 编排引擎

接收从 boundary 扫描得到的行上下文序列，按配置驱动依次执行 pass。

引擎内建遍（ADR-0006 阶段 4b）：
  - PassKind 枚举：indent/ifdef/align/wrap/comment/annotate——pass 从
    "自由 handler 函数"升格为"类型化内建遍"；
  - 量化拒绝准则：每个内建遍可声明 criterion（如对齐遍
    min_group_size/max_span、折行遍 max_width），引擎运行前检查、
    不满足则跳过该遍（布局决策显式化，cmake-format 借鉴方向）。

Doc: docs/decisions/0006-renderer-improve-roadmap.md（改进路线：阶段 3 世界 B 升级目标）
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable

from .boundary import LineContext


class PassKind(str, Enum):
    """引擎内建遍类型（类型化 pass 分类，替代自由 kind 字符串）。

    handler/category 是旧自由字符串 kind；枚举化后既有注册（kind="handler"/
    "category"）兼容映射：handler → CUSTOM、category → ALIGN。
    """

    INDENT = "indent"      # 缩进重排遍
    IFDEF = "ifdef"        # 条件编译块内容缩进遍
    ALIGN = "align"        # 品类对齐遍（column_align）
    WRAP = "wrap"          # 宽度折行遍
    COMMENT = "comment"    # 注释处理遍（wrap_comments）
    ANNOTATE = "annotate"  # 指令标注遍（ifdef_annotate）
    CUSTOM = "custom"      # 自由 handler 遍（inst_port 等）


PassFn = Callable[[list[str], list[LineContext]], list[str]]


@dataclass
class FormatterPass:
    name: str
    enabled: bool = True
    kind: str = "category"
    handler: PassFn | None = None
    category_cfg: dict | None = None
    # 量化拒绝准则（ADR-0006 阶段 4b）：运行前检查，不满足则跳过该遍
    criterion: dict | None = None

    @property
    def pass_kind(self) -> PassKind:
        """kind 字符串 → PassKind（旧值兼容映射）。"""
        try:
            return PassKind(self.kind)
        except ValueError:
            if self.kind == "handler":
                return PassKind.CUSTOM
            return PassKind.ALIGN  # "category" → 品类对齐遍


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
            # 量化拒绝准则：不满足 → 跳过该遍（布局决策显式化）
            if p.criterion and not _criterion_met(p.criterion, result, ctxs):
                continue
            # handler 优先（indent/ifdef/inst_port/wrap/comment 等内建遍
            # 均以 handler 实现）；category 是品类对齐遍（column_align）
            if p.handler:
                result = p.handler(result, ctxs)
            elif p.kind == "category" and p.category_cfg:
                result = _run_category_pass(result, ctxs, p.category_cfg)
            # 带结构行兜底（ADR-0006 阶段 3）：pass 拆行改变行数但漏同步
            # contexts（如未来新增的 handler pass）时，按就近行派生补齐，
            # 杜绝"行号漂移"（后续 pass 按 index 取 contexts 不再错位）。
            ctxs = _resync_contexts(result, ctxs)
        return result


def _criterion_met(criterion: dict, lines: list[str], contexts: list[LineContext]) -> bool:
    """量化拒绝准则检查：全部满足才运行该遍。

    支持的准则键（cmake-format 借鉴方向——布局决策显式拒绝）：
      - min_group_size: 参与行数下限（对齐遍：组内行数 < 下限 → 拒绝）
      - max_span:      参与行跨度上限（对齐遍：组间跨度 > 上限 → 拒绝）
      - max_width:     行宽上限（折行遍：无超宽行 → 拒绝）
    """
    for key, val in criterion.items():
        if key == "min_group_size":
            if len(lines) < val:
                return False
        elif key == "max_span":
            # 参与行（非空）的首尾跨度
            idxs = [i for i, l in enumerate(lines) if l.strip()]
            if idxs and (idxs[-1] - idxs[0] + 1) > val:
                return False
        elif key == "max_width":
            if not any(len(l) > val for l in lines):
                return False
    return True


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
