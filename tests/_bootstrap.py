"""tests/_bootstrap.py — 独立运行脚本/测试的公共引导。

集中两件必须在"导入任何项目模块之前"完成的事，消除各脚本手抄变体
（原 run_all_tests/run_pipeline/debug_segment_parse 及三个 e2e 测试各有一份
不同风格的 sys.path + UTF-8 样板）：

1. 项目根加入 sys.path；
2. stdout/stderr 重配置为 UTF-8（GBK(936) 控制台下中文输出乱码的根因防护）。

用法：脚本顶部先插入项目根到 sys.path，再导入本模块：

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from tests import _bootstrap  # noqa: E402

幂等：重复导入无副作用（sys.path 判重、reconfigure 可重复执行）。
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 与 tests/conftest.py 同一防护：reconfigure 仅影响本进程，比替换 sys.stdout
# 对象更安全（pytest 捕获 stdout 时不会破坏捕获器）；非 tty/受限环境拒绝则忽略。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue] — hasattr 守卫的真实运行时方法
        sys.stderr.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:  # noqa: BLE001 — 同 conftest 的取舍，忽略
        pass
