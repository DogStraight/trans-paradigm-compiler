"""checkers/macro_hygiene.py — 宏/指令卫生检查器（MH 族）。

指令级卫生检查（**解析前**，扫原始源码行而非 token 流——指令行在预处理
阶段已被剥离，不进 token 流，卫生判定必须在剥离前完成）：

    MH001  nettype 复位缺失：文件末尾生效的 nettype 指令值不是复位值
           （对齐 svlint `default_nettype_wire_at_end`——防跨文件泄漏）
    MH002  宏重定义未 undef：同名宏以**不同**值重定义
           （对齐 Verilator REDEFMACRO——**值相同不报**，仅作上下文更新）

设计要点：
- **语言知识零进代码**：指令关键字（define/undef/nettype）、指令前缀、
  复位值、续行符全部来自语言包配置（`[macro_hygiene]` + 宏识别前缀），
  引擎只按配置匹配行首指令；关键字缺省即该子检查不启用。
- **未声明配置的语言包**（如 c4）→ 检查器不注册，零开销零误报。
- **保守优先于完备**：多行宏体（续行）的值无法在单行内安全比较 →
  记为"值不确定"并不参与比较（宁可漏报不误报）。
- 分级沿用 linter 现行约定（severity=1，与 undefined-macro 等一致）；
  分级体系整体调整另行立项，不在本检查器引入分歧。

Doc: linter/linter_architecture.md（P0 指令级检查）
"""

from __future__ import annotations

from typing import Iterator

from core.define import Token

from .. import LintDiagnostic, Position
from ..checker import Checker


class MacroHygieneChecker(Checker):
    """宏/指令卫生（MH 族）——文件级检查器。"""

    def __init__(self, source: str, prefix: str, cfg: dict) -> None:
        # 文件级检查：不使用 token 区间（协议字段仅为满足 Checker 形态）
        self.start = 0
        self.end = 0
        self._source = source
        self._prefix = prefix
        self._define = str(cfg.get("define_directive") or "")
        self._undef = str(cfg.get("undef_directive") or "")
        self._nettype = str(cfg.get("nettype_directive") or "")
        self._restore = str(cfg.get("nettype_restore") or "")
        self._cont = str(cfg.get("continuation") or "")

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        del tokens  # 文件级检查：数据来自源码行，非 token 区间
        return self._check_macro_redef() + self._check_nettype()

    # ── 行扫描 ────────────────────────────────────────────

    def _iter_directives(self) -> Iterator[tuple[int, str, str, int, int]]:
        """产出 (行号, 关键字, 关键字之后原文, 缩进列, 行内容宽) 仅限指令行。

        "指令行" = strip 后以配置前缀开头（与 preprocessor 的判定同源）；
        否则视为正文（含缩进的续行、字符串内伪指令等一律不看）。
        """
        for line_idx, raw in enumerate(self._source.split("\n")):
            stripped = raw.strip()
            if not stripped or not stripped.startswith(self._prefix):
                continue
            rest = stripped[len(self._prefix):]
            parts = rest.split(None, 1)
            if not parts:
                continue
            indent = len(raw) - len(raw.lstrip())
            yield (
                line_idx,
                parts[0],
                parts[1] if len(parts) > 1 else "",
                indent,
                len(stripped),
            )

    def _diag(self, code: str, message: str, line_idx: int, indent: int, width: int) -> LintDiagnostic:
        """定位到指令行内容（含前导缩进 → 行宽），便于编辑器整行高亮。"""
        return LintDiagnostic(
            range=(Position(line_idx, indent), Position(line_idx, indent + width)),
            severity=1,
            code=code,
            message=message,
        )

    # ── MH002：宏重定义未 undef ──────────────────────────

    def _check_macro_redef(self) -> list[LintDiagnostic]:
        if not (self._define and self._undef):
            return []  # 语言包未声明宏指令关键字 → 本子检查不启用
        errors: list[LintDiagnostic] = []
        seen: dict[str, str | None] = {}

        for line_idx, kw, rest, indent, width in self._iter_directives():
            if kw == self._define:
                name, body = _split_name_body(rest)
                if not name:
                    continue
                # 多行宏体（续行）跨行，单行比较不安全 → 值不确定
                value = None if (self._cont and body.endswith(self._cont)) else body
                if name in seen:
                    prev = seen[name]
                    if prev is not None and value is not None and prev != value:
                        errors.append(
                            self._diag(
                                "MH002",
                                f"宏 '{name}' 以不同值重定义（'{prev}' → '{value}'）"
                                f"——重定义前应先用 {self._prefix}{self._undef} "
                                f"{name} 表明意图",
                                line_idx,
                                indent,
                                width,
                            )
                        )
                seen[name] = value
            elif kw == self._undef:
                name, _ = _split_name_body(rest)
                if name:
                    seen.pop(name, None)
        return errors

    # ── MH001：nettype 复位缺失 ──────────────────────────

    def _check_nettype(self) -> list[LintDiagnostic]:
        if not (self._nettype and self._restore):
            return []  # 语言包未声明 nettype 指令 → 本子检查不启用
        last: tuple[int, str, int, int] | None = None

        for line_idx, kw, rest, indent, width in self._iter_directives():
            if kw != self._nettype:
                continue
            value, _ = _split_name_body(rest)
            last = (line_idx, value, indent, width)

        if last is None:
            return []  # 未使用该指令 → 无"未复位"问题
        line_idx, value, indent, width = last
        if value == self._restore:
            return []  # 末尾已复位
        return [
            self._diag(
                "MH001",
                f"文件末尾生效的 {self._prefix}{self._nettype} 为 '{value}'"
                f"（未复位为 '{self._restore}'）——可能泄漏到同编译单元的后续文件",
                line_idx,
                indent,
                width,
            )
        ]


def _split_name_body(rest: str) -> tuple[str, str]:
    """把"关键字之后的原文"拆成 (名字/值, 主体)。无空白则主体为空串。"""
    parts = rest.split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1].strip() if len(parts) > 1 else ""
