"""number_runner.py — 配置驱动的数字解析器（唯一路径）

从语言包声明的数字形态（lexer.number）编译 FSM，提供数字解析入口。

行为（P2.1 基线锁定的真实行为）：
  - 多 pattern 最长匹配（size 形态 + 无 size 形态独立编译，取最长 token）
  - Verilog 特有：'h/'d/'b/'o 后允许空格（32'h ffff_ffff）、跨空格 ? 是三元
    运算符（4'b1?0 紧跟才合法）、尾随下划线修剪
  - 与旧 NumberFSM 相同的"多 pattern 各自从 start 走"语义

旧 NumberFSM（number_fsm.py）回退路径已移除（P2.1 配置化后所有语言包都
声明数字形态，回退不可达且带过度匹配 bug：0x1F 被误认整体）。数字形态
缺失由 Lexer 构造处 fail-fast（decisions/0003）。
Doc: docs/language_walkthrough.md（数字形态扫描）
"""

from __future__ import annotations

from .number_gen import (
    compile_patterns,
    char_category,
    NumberPattern,
)

# value 态后允许跨过的空白字符（形态声明允许时）
_SPACE_CHARS = (" ", "\t")


class _ConfigNumberRunner:
    """配置驱动的数字解析器：多 pattern 最长匹配。"""

    def __init__(self, configs: list[dict]):
        self.patterns = compile_patterns(configs)

    def run(self, text: str, start_pos: int) -> tuple[str, int]:
        """从 start_pos 解析数字字面量，返回 (token, end_pos)。

        多 pattern 各自从 start 走，取最长 token（类似旧 NumberFSM 的
        单 pattern + 内部多分支，但这里 pattern 独立）。
        """
        best: tuple[str, int] = ("", start_pos)
        for pat in self.patterns:
            tok, end = self._run_pattern(pat, text, start_pos)
            if tok and len(tok) > len(best[0]):
                best = (tok, end)
        return best

    def starts_at_declared_non_digit(self, text: str, pos: int) -> bool:
        """是否有**显式声明非数字起始**的形态（`lead_dot`）能从这里开始。

        只认显式声明过的形态：把"任何声明的起始字符"都先试数字扫描会**劫持同字符
        符号**——yaml 的 `yaml_neg`（`-` 前缀形态）会让序列指示符 `- 8080` 的 `-`
        变成 `literal.number`（实测 18 处 yaml 测试变红）。故 C 的 `.5` 需要
        `lead_dot = true` 显式表态，未表态的形态（含 yaml 的 `-`）行为零变化。
        """
        if pos >= len(text):
            return False
        cat = char_category(text[pos])
        if cat is None:
            return False
        return any(
            p.lead_dot and (p.start_state, cat) in p.transitions
            for p in self.patterns
        )

    @staticmethod
    def _value_states(pat: NumberPattern) -> set[int]:
        """空格跳过的目标态：仅 value 态（base 字母后的进制值态），不含 size
        态（十进制整数）——整数后空格是分隔符不是续值。"""
        return set(pat.base_states.values()) or pat.accepting

    @staticmethod
    def _should_break(ch: str, prev_underscore: bool, after_space: bool) -> bool:
        """当前字符是否直接终止扫描：连续下划线 / 跨空格的三元 `?` 基值。"""
        if ch == "_" and prev_underscore:
            return True
        return after_space and ch == "?"

    @staticmethod
    def _next_state(pat: NumberPattern, state: int, ch: str) -> int | None:
        """单字符转移目标（无该字符类别或该转移 → None = 终止）。"""
        cat = char_category(ch)
        return pat.transitions.get((state, cat)) if cat else None

    @staticmethod
    def _token_before(text: str, start_pos: int, last_accept: int) -> tuple[str, int]:
        """截取到最近接受位并去掉尾随下划线；无接受位/修剪后为空 → ("", start_pos)。"""
        if last_accept <= start_pos:
            return "", start_pos
        trimmed = text[start_pos:last_accept].rstrip("_")
        if trimmed:
            return trimmed, start_pos + len(trimmed)
        return "", start_pos

    def _run_pattern(
        self, pat: NumberPattern, text: str, start_pos: int
    ) -> tuple[str, int]:
        if start_pos >= len(text):
            return "", start_pos
        # 起始字符：pattern 的 start 态必须有转移才走
        state = pat.start_state
        i = start_pos
        last_accept = start_pos
        prev_underscore = False
        after_space = False

        # 允许空格跳过（'h/'d/'b/'o 后 32'h ffff_ffff）：仅引号类形态
        allow_space = pat.allow_space_after_quote
        value_states = self._value_states(pat)

        while i < len(text):
            ch = text[i]
            if self._should_break(ch, prev_underscore, after_space):
                break
            # value 态后允许空格（32'h ffff_ffff）——仅形态声明允许时
            if allow_space and state in value_states and ch in _SPACE_CHARS:
                i += 1
                after_space = True
                continue
            after_space = False
            nxt = self._next_state(pat, state, ch)
            if nxt is None:
                break
            state = nxt
            prev_underscore = ch == "_"
            i += 1
            if state in pat.accepting:
                last_accept = i
        last_accept = self._consume_suffix(pat, text, last_accept, start_pos)
        return self._token_before(text, start_pos, last_accept)

    @staticmethod
    def _consume_suffix(
        pat: NumberPattern, text: str, last_accept: int, start_pos: int
    ) -> int:
        """消费形态声明的**尾随后缀**（C 的 `1UL` / `1.5f` / `0x1Fu`）→ 新的接受位。

        后缀是 DFA 之后的声明式尾段（`suffix = { chars, max }`），不是 DFA 转移：
        理由见 `number_gen.compile_number_pattern`（全局字符类别里 `f`/`F` 已是
        十六进制 digit，按类别加边会撞键）。未声明后缀的形态（verilog）走空集，
        行为与本键不存在时逐字一致。

        只在已有接受位之后消费（无匹配则原样返回）；超额字符留给下一个 token
        （`1u2` → `1u` + `2`，与"数字后跟标识符"同形）。后缀**组合合法性**
        （`1UL` 合法、`1ff` 非法）不在词法层判定——C 的 pp-number 本就宽进，
        约束归语义层。
        """
        if not pat.suffix_chars or pat.suffix_max <= 0 or last_accept <= start_pos:
            return last_accept
        i, taken = last_accept, 0
        while (
            i < len(text)
            and taken < pat.suffix_max
            and text[i] in pat.suffix_chars
        ):
            i += 1
            taken += 1
        return i


def build_number_runner(
    configs: list[dict] | None = None,
) -> _ConfigNumberRunner | None:
    """构建数字解析器（配置驱动唯一路径）。

    Args:
        configs: 数字形态声明列表（[[number.based]]）。空/None → 返回 None，
            由 Lexer 构造处 fail-fast 报错（形态缺失 = 配置错误）。

    Returns:
        _ConfigNumberRunner 或 None（形态未声明，调用方负责 fail-fast）。
    """
    if configs:
        return _ConfigNumberRunner(configs)
    return None
