"""islands — 片段模式（P1）：语法配置驱动的岛式分片与局部管线变换。

定位（作者 2026-10-30 定稿契约）：

- **无声明面**：岛不是配置项——片段模式下，语言包语法配置推导出的语法单元默认就是岛；
- **无记号/范围可选模式**：要限定"只有某部分语法有效"，单开一个语言包；
- **岛内只走真实管线**（parse + render，可选 transform/check 由管线开关决定），不另造
  近似规则；
- **water**（未被岛覆盖的 token / 未识别区 / 含宏与指令行的区间）逐字节原样保留；
- **后验默认开**：岛级重解析 + 双跑幂等；无岛/零变化 ⇒ 逐字节返回原 bytes。

推导链复用 linter 的内部组件（`linter.discovery` 等），本包只做"分片 → 管线 → 合成"。

Doc: docs/gaps/gap-fragment-mode.md
"""

from .rewrite import RewriteResult, print_diff, rewrite_bytes, rewrite_file

__all__ = ["RewriteResult", "print_diff", "rewrite_bytes", "rewrite_file"]
