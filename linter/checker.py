"""checker.py — 扁平检查器协议、注册表与轻量 AST 节点。

发现阶段（discovery.py）把 token 流变形成"自动注册形态"——即轻量 AST
节点列表（DiscoveredNode）。每个节点在检查阶段被实例化为对应的 Checker，
统一调用 validate() 做扁平验证。

架构目标：
    发现一次 → 注册扁平检查器列表 → 逐个 validate → 合并错误
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.define import Token

from . import LintDiagnostic

# 顶层上下文（发现入口）：块内上下文由 opener_context 配置动态生成，不硬编码
CTX_TOP = "top"


@runtime_checkable
class Checker(Protocol):
    """扁平检查器协议：每个实例只检查一种语法结构。"""

    start: int  # 检查的 token 区间起点（含）
    end: int    # 检查的 token 区间终点（不含）

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        """在自身区间内做语法验证，返回错误列表。"""
        ...


@dataclass
class DiscoveredNode:
    """轻量 AST 节点 — 发现阶段的产物（自动注册的检查器描述）。

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
        """扁平验证所有已注册检查器，合并错误。"""
        errors: list[LintDiagnostic] = []
        for checker in self._checkers:
            try:
                errors += checker.validate(tokens)
            except Exception:
                # 单个检查器失败不影响其他（扁平架构的解耦收益）
                continue
        return errors
