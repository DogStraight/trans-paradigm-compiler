"""checkers/style.py — 排版卫生检查器（ST 族）。

**解析前**按原始源码行做排版检查（与 MH 族同层：排版事实在字符层，
token 化不提供尾随空白/行长信息）：

    ST001  尾随空白：行尾（换行前）存在空格或制表符
    ST002  制表符：行内（非尾随区）出现 tab 字符——缩进请用空格
    ST003  行长超限：行字符数超过配置上限（0 = 不检）

设计要点：
- **语言知识零进代码**：三个子检查各自以配置字段开关，宽度上限来自
  语言包（`[style_check].max_line_width`，与 formatter 折行阈值同值约定），
  引擎只做字符级判定。
- **未声明配置的语言包**（c4/yaml）→ 检查器不注册，零开销零误报。
- **无重叠**：尾随制表符计入 ST001（行尾空白），ST002 只报非尾随区——
  同一处不双报。
- 分级：severity=2（风格提示）且 **blocking=False**——排版事实不影响
  解析，不阻断语义阶段、不计失败退出（与 MH 族的 severity=1/阻断语义
  不同：后者是“错误”性的指令卫生）；linter 整体分级体系调整另行立项。
- 边界（v1 简化，随文档记录）：ST002 按行扫字符串字面量内的 tab 同样
  计入（罕见；精确豁免需 token 区间，按需再收）。
- 行长按**字符数**计（tab 计 1）；tab 展开列宽是另一套规范，v1 不做。

Doc: linter/linter_architecture.md（P0 行级检查）
"""

from __future__ import annotations

from dataclasses import dataclass

from core.define import Token

from .. import LintDiagnostic, Position
from ..checker import Checker

# 行尾空白集合（尾随区判定；与 ST002 的豁免区共用）
_TRAILING_CHARS = " \t"


@dataclass(frozen=True)
class _LineFacts:
    """一行源码的排版事实（ST 三查共用）。"""

    line: str      # 去 CRLF 的 \r 后的行内容
    content: str   # 去行尾空白后的内容

    @classmethod
    def of(cls, raw: str) -> "_LineFacts | None":
        """从原始行构造；空行返回 None（空行不参与三查）。"""
        line = raw.rstrip("\r")  # CRLF：\r 不算行内容
        if not line:
            return None
        return cls(line=line, content=line.rstrip(_TRAILING_CHARS))


class StyleChecker(Checker):
    """排版卫生（ST 族）——文件级检查器。"""

    def __init__(self, source: str, cfg: dict) -> None:
        # 文件级检查：不使用 token 区间（协议字段仅为满足 Checker 形态）
        self.start = 0
        self.end = 0
        self._source = source
        self._trailing = bool(cfg.get("trailing_whitespace", False))
        self._tab = bool(cfg.get("tab_character", False))
        self._max_width = int(cfg.get("max_line_width") or 0)

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        del tokens  # 文件级检查：数据来自源码行，非 token 区间
        errors: list[LintDiagnostic] = []
        for line_idx, raw in enumerate(self._source.split("\n")):
            facts = _LineFacts.of(raw)
            if facts is None:
                continue
            errors.extend(self._check_line(line_idx, facts))
        return errors

    def _check_line(self, line_idx: int, facts: _LineFacts) -> list[LintDiagnostic]:
        """单行三查：ST001 尾随空白 → ST002 行内制表符 → ST003 行长超限。"""
        return (
            self._check_trailing_ws(line_idx, facts)
            + self._check_tab_char(line_idx, facts)
            + self._check_line_width(line_idx, facts)
        )

    def _check_trailing_ws(
        self, line_idx: int, facts: _LineFacts
    ) -> list[LintDiagnostic]:
        """ST001 尾随空白：行尾（换行前）存在空格或制表符。"""
        n_trail = len(facts.line) - len(facts.content)
        if not self._trailing or n_trail == 0:
            return []
        return [
            self._diag(
                "ST001",
                f"行尾存在空白（{n_trail} 个字符）",
                line_idx,
                len(facts.content),
                len(facts.line),
            )
        ]

    def _check_tab_char(
        self, line_idx: int, facts: _LineFacts
    ) -> list[LintDiagnostic]:
        """ST002 制表符：非尾随区（尾随区已由 ST001 覆盖，不双报）。"""
        if not self._tab:
            return []
        tab_at = facts.content.find("\t")
        if tab_at < 0:
            return []
        count = facts.content.count("\t")
        suffix = f"（本行 {count} 处）" if count > 1 else ""
        return [
            self._diag(
                "ST002",
                f"行内使用制表符，缩进请用空格{suffix}",
                line_idx,
                tab_at,
                tab_at + 1,
            )
        ]

    def _check_line_width(
        self, line_idx: int, facts: _LineFacts
    ) -> list[LintDiagnostic]:
        """ST003 行长超限：上限为 0 时不检。"""
        if not self._max_width or len(facts.line) <= self._max_width:
            return []
        return [
            self._diag(
                "ST003",
                f"行宽 {len(facts.line)} 字符，超过上限 {self._max_width}",
                line_idx,
                self._max_width,
                len(facts.line),
            )
        ]

    # ── 诊断构造 ──────────────────────────────────

    def _diag(
        self, code: str, message: str, line_idx: int, col: int, end_col: int
    ) -> LintDiagnostic:
        """定位到行内区间（尾随空白/制表符/超长段），便于编辑器高亮。

        severity=2（风格提示）+ blocking=False（不阻断语义/不计失败
        退出）——排版事实不影响解析，与语法类诊断（severity=1、
        blocking 缺省 True）消费语义不同。
        """
        return LintDiagnostic(
            range=(Position(line_idx, col), Position(line_idx, end_col)),
            severity=2,
            code=code,
            message=message,
            blocking=False,
        )
