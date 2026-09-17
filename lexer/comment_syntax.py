"""注释语法（语言包声明驱动）——引擎读取注释标点的唯一入口。

注释形态由语言包声明（`[comment] pairs` / `[[capture]]`，经
`lexer/capture_runner.py` 归一化），引擎不认识标点本身：verilog 是
`//` + `/* */`，yaml 是 `#`，c4 是 `//` 与 `#`（且无块注释）。本模块把声明
归一成两类消费面：

  - **书写**（写出一条注释）：`line_start` / `block_open` / `block_close`
    ——引擎内部占位 marker 与任何"以注释形态穿过管线"的内容都从这里取标点
    （`preprocessor/_markers.py` 是唯一消费者）；
  - **扫描**（推注释跨度）：`block_pairs`（跨行成对定界符）+ `line_starts`
    （行注释起始标记）——行级状态机（预处理器指令扫描，见
    `preprocessor/_expand.py`）用。

未声明注释形态的语言包 → 各字段为空（未声明 = 没有注释，不是错误）；真正
需要写注释时（marker 书写）由消费者 fail-fast（配置缺失不静默降级）。

按 rules_dir 缓存（同 Lexer：自包含解析，不依赖最后一次 load_all）。
Doc: preprocessor/README.md（指令扫描的注释跨度）
Doc: docs/pipeline_stages.md（预处理器阶段）
"""

import os

from core.token_protocol import COMMENT_TOKEN_TYPE

# 缓存键 = rules_dir（纯声明归一，同参结果恒定）
_CACHE: dict[str, "CommentSyntax"] = {}


class CommentSyntax:
    """一种语言的注释标点（全部来自语言包声明）。

    - `line_start`：行注释起始标记（`kind = line` 的首条），如 `//`；无则 None
    - `block_open` / `block_close`：成对定界符（`kind = marker` 的首条），如 `/*` / `*/`
    - `block_pairs` / `line_starts`：**全部**声明项，供跨度扫描用（可能有多种，
      如 c4 的 `//` 与 `#` 都是行注释）
    """

    def __init__(
        self,
        *,
        block_pairs: tuple[tuple[str, str], ...],
        line_starts: tuple[str, ...],
    ) -> None:
        self.block_pairs = block_pairs
        self.line_starts = line_starts

    @property
    def line_start(self) -> str | None:
        """书写用行注释起始标记（未声明行注释 → None）。"""
        return self.line_starts[0] if self.line_starts else None

    @property
    def block_open(self) -> str | None:
        """书写用块注释起始定界符（未声明成对定界符 → None）。"""
        return self.block_pairs[0][0] if self.block_pairs else None

    @property
    def block_close(self) -> str | None:
        """书写用块注释结束定界符（未声明成对定界符 → None）。"""
        return self.block_pairs[0][1] if self.block_pairs else None

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"CommentSyntax(block_pairs={self.block_pairs!r}, "
            f"line_starts={self.line_starts!r})"
        )


def load_comment_syntax(rules_dir: str) -> CommentSyntax:
    """按语言包解析注释标点（缓存；与 Lexer 同源同参）。

    与 Lexer 同源：`ConfigRegistry.resolve(rules_dir)` → `merge_token_define` →
    `capture_runner.build_rules` 归一化后按 kind 分流：
      - `marker`（如 `/* … */`）→ 成对定界符（可跨行）；
      - `line`（如 `// … 换行`）→ 行注释起始标记（行内即终止）。
    """
    cached = _CACHE.get(rules_dir)
    if cached is not None:
        return cached

    from core.config_registry import ConfigRegistry
    from lexer.capture_runner import CaptureRunner
    from lexer.lexer_utils import merge_token_define

    resolved = ConfigRegistry.resolve(
        rules_dir, plugins_dir=os.path.join(rules_dir, "plugins")
    )
    token_define = merge_token_define(resolved)
    rules = [
        rule
        for rule in CaptureRunner.build_rules(token_define)
        if rule.token_type == COMMENT_TOKEN_TYPE
    ]
    syntax = CommentSyntax(
        block_pairs=tuple(
            (r.start, r.end) for r in rules if r.kind == "marker" and r.end
        ),
        line_starts=tuple(r.start for r in rules if r.kind == "line" and r.start),
    )
    _CACHE[rules_dir] = syntax
    return syntax
