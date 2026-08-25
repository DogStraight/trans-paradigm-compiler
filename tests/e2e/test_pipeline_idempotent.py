"""管线级幂等检查回归测试。

幂等语义：非展开路径下，生成文本应能被完整管线再次稳定处理（第二遍
parse 无 truncated）。坏文本（如 formatter 拆 `==` 成 `= =`）会让第二遍
parse 软失败/truncated → idempotent=False。

展开路径（宏表/占位符/指令行任一存在）跳过幂等——宏体替换、条件分支
选择、注释锚点漂移都使第二遍内容必然不同，那是展开语义，不是幂等性问题。
"""

import os
import sys

# 项目根 + stdout UTF-8（必须在 import core 之前）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport] — 副作用导入（sys.path + UTF-8）

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
_NORMAL_ALU = os.path.join(_SAMPLES, "normal", "ref", "ref_alu.v")
_MACRO_DEF = os.path.join(_SAMPLES, "macro", "ref", "ref_macro_def.v")


def _run(path: str, **kw) -> dict:
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return run_pipeline_on_source(source=src, input_path=path, quiet=True, **kw)


def test_non_expanded_idempotent():
    """非展开路径：normal 样例输出可再次被管线稳定处理。"""
    r = _run(_NORMAL_ALU)
    assert r["success"], r.get("error", "pipeline failed")
    assert r.get("idempotent") is True


def test_expanded_path_skips_idempotency():
    """展开路径跳过幂等（内容变化是预期，不误报 idempotent=False）。"""
    r = _run(_MACRO_DEF, expand_macros=True)
    assert r["success"], r.get("error", "pipeline failed")
    assert r.get("idempotent") is True


def test_bad_equal_equal_fails_idempotency():
    """坏输出 `= =`（formatter 把 `==` 拆开）第二遍 parse 必然 truncated。

    幂等判据：输出再走一遍完整管线不 truncated。坏输出（`= =`）会让第二遍
    parse 软失败/truncated → 幂等 FAIL。这里直接对坏输出跑管线验证判据命中
    （check_idempotent=False：只看第二遍 parse 本身，不看它自己输出的幂等）。
    """
    r = _run(_NORMAL_ALU)
    assert r["success"]
    assert r.get("idempotent") is True
    assert "==" in r["output"], "样例需含 == 以构造坏文本"
    bad = r["output"].replace("==", "= =", 1)

    r2 = run_pipeline_on_source(
        source=bad,
        input_path=_NORMAL_ALU,
        quiet=True,
        expand_macros=False,
        no_lint=True,
        check_idempotent=False,
    )
    p2 = r2.get("parser")
    truncated = bool(getattr(p2, "_parse_truncated", False)) if p2 else True
    assert truncated, "坏输出第二遍应 truncated（幂等判据命中）"
