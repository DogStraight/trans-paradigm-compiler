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
"""

from __future__ import annotations

from .number_gen import (
    compile_patterns,
    char_category,
    NumberPattern,
)


class ConfigNumberRunner:
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
        # 空格跳过的目标态：仅 value 态（base 字母后的进制值态），
        # 不含 size 态（十进制整数）——整数后空格是分隔符不是续值
        value_states = set(pat.base_states.values())
        if not value_states:
            value_states = pat.accepting

        while i < len(text):
            ch = text[i]
            # 禁止连续下划线
            if ch == "_" and prev_underscore:
                break
            # value 态后允许空格（32'h ffff_ffff）——仅形态声明允许时
            if allow_space and state in value_states and (ch == " " or ch == "\t"):
                i += 1
                after_space = True
                continue
            # 跨空格不允许 '?' 基值（三元运算符）
            if after_space and ch == "?":
                break
            after_space = False
            cat = char_category(ch)
            nxt = pat.transitions.get((state, cat)) if cat else None
            if nxt is None:
                break
            state = nxt
            prev_underscore = ch == "_"
            i += 1
            if state in pat.accepting:
                last_accept = i
        if last_accept > start_pos:
            token = text[start_pos:last_accept]
            trimmed = token.rstrip("_")
            if trimmed:
                return trimmed, start_pos + len(trimmed)
        return "", start_pos


def build_number_runner(configs: list[dict] | None = None):
    """构建数字解析器（配置驱动唯一路径）。

    Args:
        configs: 数字形态声明列表（[[number.based]]）。空/None → 返回 None，
            由 Lexer 构造处 fail-fast 报错（形态缺失 = 配置错误）。

    Returns:
        ConfigNumberRunner 或 None（形态未声明，调用方负责 fail-fast）。
    """
    if configs:
        return ConfigNumberRunner(configs)
    return None
