"""oracle.py — fuzz 不变量（单一来源）。

`run_fuzz.py`（找）与 `shrink.py`（最小化 / 沉淀）必须**用同一份不变量**：
最小化的判据是"这段输入是否仍触发同一个违反"，判据一变，缩出来的东西就不是
原来那个 bug 了。故把不变量抽到这里，两边都 import 本模块。

语言包感知：管线要按**目标语言包**跑（`rules_dir` / `ext_dirs`），否则
"用 C 生成器 + 用 verilog 格式化"会产出满屏假 finding。词法侧同参。

Doc: tests/fuzz/README.md（不变量清单与已知良性类）
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.token_protocol import TRIVIA_TOKEN_TYPES

# ── 违反类别 ────────────────────────────────
# kind 是**机器可读**的判据键：最小化要"保留同一 kind"，沉淀要按它取文件名/抬头。
# 新增类别时同步 README「不变量」表与 `EXPECTATION`（沉淀时的期望行为）。
CRASH = "crash"                  # 管线抛异常（硬违规）
SILENT_FAIL = "silent-fail"      # success=False 且 error 为空（静默失败）
TOKENIZE_FAIL = "tokenize-fail"  # 合法输入格式化后不可 token 化
TOKEN_CORRUPT = "token-corrupt"  # 格式化改变了非 trivia token 序列
IDEM_CRASH = "idem-crash"        # 二次格式化崩溃
NON_IDEMPOTENT = "non-idempotent"  # format(format(x)) != format(x)

ALL_KINDS = (
    CRASH,
    SILENT_FAIL,
    TOKENIZE_FAIL,
    TOKEN_CORRUPT,
    IDEM_CRASH,
    NON_IDEMPOTENT,
)

# 宏指令 marker：带宏的输入不走 token 保序判据（展开/还原本就改 token 流，
# 见 README「已知的 oracle 判定」）。与 `run_fuzz` 历史行为一致。
MACRO_MARKERS = (
    "`ifdef", "`ifndef", "`define", "`include", "`else", "`elsif", "`endif",
    "`timescale", "`resetall", "`celldefine",
)


@dataclass(frozen=True)
class Violation:
    """一条不变量违反：kind 为判据键，detail 为现场描述（人读）。"""

    kind: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind.upper()}] {self.detail}"


def ext_dirs_for(rules_dir: str) -> list[str]:
    """语言包的插件目录约定：`<pack>/plugins`（存在才算）。

    与 `LinterScanner` / 各语言包 conftest 的惯例一致：包 `tpc.toml` 列了插件却
    不传 ext_dirs 会 fail-fast，故此处按目录存在性自动带上。
    """
    plugins = os.path.join(rules_dir, "plugins")
    return [plugins] if os.path.isdir(plugins) else []


def format_source(src: str, rules_dir: str, ext_dirs: list[str] | None = None) -> dict:
    """按 `format` 指令的管线设置跑一次（与 main.py format 同参）。"""
    from pipeline import run_pipeline_on_source

    return run_pipeline_on_source(
        source=src,
        quiet=True,
        expand_macros=True,
        analyzer_enabled=False,
        transform_enabled=False,
        renderer_enabled=True,
        parse_enabled=True,
        no_lint=False,
        format_output=True,
        rules_dir=rules_dir,
        ext_dirs=ext_dirs_for(rules_dir) if ext_dirs is None else ext_dirs,
    )


def token_seq(text: str, lexer):
    """非 trivia token 序列；不可 token 化 → None（由调用方判"哪一侧坏"）。"""
    try:
        toks = lexer.tokenize(text)
    except Exception:
        return None
    return [(t.type, t.content) for t in toks if t.type not in TRIVIA_TOKEN_TYPES]


def evaluate_format(
    src: str,
    lexer,
    *,
    rules_dir: str,
    ext_dirs: list[str] | None = None,
    label: str = "gen",
) -> list[Violation]:
    """跑全部不变量，返回违反清单（空 = 通过）。

    `label` 只影响 token 保序判据的适用范围：语法驱动生成的**合法**程序才断言
    "格式化不改内容"；变异产物多是畸形输入，容错解析路径（补分号/重构结构）会
    合法地改变 token 序列（README「已知的 oracle 判定」）。
    """
    violations: list[Violation] = []
    try:
        r = format_source(src, rules_dir, ext_dirs)
    except Exception as exc:  # 崩溃 = 违反
        return [Violation(CRASH, f"{label}: {type(exc).__name__}: {exc}")]

    if not r.get("success"):
        if not r.get("error"):
            violations.append(
                Violation(SILENT_FAIL, f"{label}: success=False 且无 error")
            )
        return violations

    out = r.get("output", "")
    if not out:
        return violations

    if label == "gen" and not any(m in src for m in MACRO_MARKERS):
        seq_in = token_seq(src, lexer)
        seq_out = token_seq(out, lexer)
        if seq_in is not None and seq_out is None:
            violations.append(
                Violation(TOKENIZE_FAIL, f"{label}: 格式化输出无法 token 化")
            )
        elif seq_in is not None and seq_out is not None and seq_in != seq_out:
            violations.append(
                Violation(
                    TOKEN_CORRUPT,
                    f"{label}: 格式化改变了 token 序列 "
                    f"(in {len(seq_in)} → out {len(seq_out)} tokens)",
                )
            )

    try:
        r2 = format_source(out, rules_dir, ext_dirs)
    except Exception as exc:
        violations.append(Violation(IDEM_CRASH, f"{label}: 二次格式化崩溃: {exc}"))
        return violations
    if r2.get("success") and r2.get("output") != out:
        violations.append(
            Violation(NON_IDEMPOTENT, f"{label}: format(format(x)) != format(x)")
        )
    return violations


def expectation_of(src: str, rules_dir: str, ext_dirs: list[str] | None = None) -> str:
    """沉淀判据：这段输入在**当前**代码下的应有行为。

    - `clean`  — 格式化成功（→ edge 语料 clean/）
    - `reject` — 失败且带 error（→ edge 语料 reject/）
    - `unfixed`— 仍违反不变量或崩溃：**不能沉淀**（写进去会让 edge 门禁变红，
      而且它本来就还没修）
    """
    try:
        r = format_source(src, rules_dir, ext_dirs)
    except Exception:
        return "unfixed"
    if r.get("success"):
        return "clean"
    return "reject" if r.get("error") else "unfixed"
