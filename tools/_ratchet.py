"""_ratchet.py — ratchet/门禁的「全量消失」判据（**单一实现**，不许复制）。

为什么有它（外部证伪 F1，2026-11-07 实测）：`tools/structural_score.py` 在 bifrost 报表
为空时，把基线 78 项全部记作「消除」并 exit 0——ratchet 分不清"债还完了"和"量具死了"。
这不是某一个工具的洞，是**所有 ratchet 的共同形状**：只要「当前集合为空 ⇒ 没有违规
⇒ 绿」，量具/扫描面一坏，门禁就变成装饰。

判据（作者 2026-11-07 批准，见 `policy/structural_budget.md`「全量消失判据」）：

    基线项集合非空、当前集合为空 ⇒ FAIL（exit 2），不得解释为「欠账清零」。

真要归零的唯一合法路径是 `--save` / `--record` **显式重录基线**（留下审计痕迹）。

> 与「空扫描面」判据的分工：本模块管**基线→当前**的对比型 ratchet；工具自己扫描面
> 塌陷（扫到 0 个文件）由各工具自带下限（如 `check_platform_encoding.MIN_PY_FILES`）兜。
"""
from __future__ import annotations

import sys

#: 消息里必须给出的合法归零路径（各工具 `--save` / `--record` 名字不同，写通用两种）。
RECORD_HINT = "真要归零请先 --save / --record 显式重录基线（留审计痕迹）"


def guard_not_vanished(label: str, baseline_n: int, current_n: int) -> int:
    """基线非空而当前为空 → 打印理由并返回 2；正常返回 0。

    **返回退出码而不是 raise**：本模块是库函数，不该替调用方决定进程怎么退——
    CLI 直接 `return` 它，pytest 用例 `assert ... == 0`。这条是实测教训：第一版
    `raise SystemExit(2)` 直接打红了既有的 `test_compare_all_items_gone_fails_closed`
    （那条契约是「`_compare` 返回 2」）。

    Args:
        label: 谁在报（进消息，便于定位是哪条 ratchet 的量具坏了）。
        baseline_n: 基线项数。
        current_n: 本次实际产出的项数。

    Returns:
        0 = 正常；2 = 全量消失（已向 stderr 写明理由）。
    """
    if baseline_n > 0 and current_n == 0:
        sys.stderr.write(
            f"[FAIL] 全量消失（{label}）：基线有 {baseline_n} 项、当前 0 项"
            f"——疑似报表/扫描面失效，拒绝当绿（{RECORD_HINT}）\n"
        )
        return 2
    return 0
