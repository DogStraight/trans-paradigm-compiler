"""checker.py — 扁平检查器协议、注册表与发现节点。

发现阶段（`linter/discovery.py`，本包的语言无关推导组件）把 token 流变形成轻量
结构树（`DiscoveredNode`）；本模块按节点实例化 Checker，统一调用 validate() 做
扁平验证。

Doc: linter/linter_architecture.md

架构目标：
    发现一次 → 注册扁平检查器列表 → 逐个 validate → 合并错误
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.define import Token

from . import LintDiagnostic, Position, token_pos

# 顶层上下文（发现入口）：块内上下文名不参与候选筛选（B 类 ident 候选是单一全局
# 集合，靠 Level 1 前瞻 / Level 2 试解析精确筛选），context 仅作节点归属标记
CTX_TOP = "top"


@dataclass
class DiscoveredNode:
    """轻量 AST 节点 — 发现阶段的产物。

    不包含完整 AST 信息（无属性绑定、无符号表），只记录：
    发现了什么语法（rule）、在哪个 token 区间（start/end）、
    属于什么块上下文（context）、以及嵌套发现的子结构（children）。
    """

    type: str              # "bound" | "statement" | "token"
    rule: "str | list[str]"  # 同一起始 token 的多个候选规则（如 TaskDeclANSI/Old）
    start: int
    end: int
    context: str = CTX_TOP
    children: list["DiscoveredNode"] = field(default_factory=list)


@dataclass(frozen=True)
class UnrecognizedSite:
    """未识别语句位点（token 索引 + 说明）；消费方自行决定诊断或 water。"""

    start: int
    message: str


@runtime_checkable
class Checker(Protocol):
    """扁平检查器协议：每个实例只检查一种语法结构。"""

    start: int  # 检查的 token 区间起点（含）
    end: int    # 检查的 token 区间终点（不含）

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        """在自身区间内做语法验证，返回错误列表。"""
        ...


class CheckerRegistry:
    """已注册检查器的扁平列表。"""

    def __init__(self) -> None:
        self._checkers: list[Checker] = []

    def add(self, checker: Checker) -> None:
        self._checkers.append(checker)

    @property
    def checkers(self) -> list[Checker]:
        return self._checkers

    def __len__(self) -> int:
        return len(self._checkers)

    def validate_all(self, tokens: list[Token]) -> list[LintDiagnostic]:
        """扁平验证所有已注册检查器，合并错误。

        单个检查器失败不影响其他（扁平架构的解耦收益），但**不静默吞掉**：
        异常转为 linter-internal-error 诊断，使检查器崩溃可见——否则合法样本
        会因检查器崩溃而"不报错=绿"（虚假绿，生产事故温床）。诊断 message
        记录检查器类型与异常，便于定位。
        """
        errors: list[LintDiagnostic] = []
        for checker in self._checkers:
            try:
                errors += checker.validate(tokens)
            except Exception as exc:  # noqa: BLE001 — 取 token 失败时降级到默认位置，诊断仍产出
                t = tokens[0] if tokens else None
                pos = token_pos(t) if t else Position(0, 0)
                errors.append(
                    LintDiagnostic(
                        range=(pos, pos),
                        message=(
                            f"linter internal error in {type(checker).__name__}: {exc}"
                        ),
                        severity=1,
                        code="linter-internal-error",
                    )
                )
        return errors
