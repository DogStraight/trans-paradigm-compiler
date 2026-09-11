"""单元执行轨迹（0.1.2 阶段 6 可视化切片）：时点 = 可视化断点。

记录"谁在哪个时点跑了、向黑板（extra）写了哪些键"——ADR-0015 §2 硬要求
（配对隐式为设计，但产物必须可视化）。落 `ctx.result["trace"]`；
`sym_json` 指定时同目录写 `trace.json`。
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

_SRC = "module m;\n  wire a;\n  assign a = 1'b0;\nendmodule\n"


def _run():
    return run_pipeline_on_source(source=_SRC, quiet=True, no_lint=True)


def test_trace_present_and_shaped() -> None:
    res = _run()
    assert res["success"], res.get("error")
    trace = res.get("trace")
    assert isinstance(trace, list) and trace, "trace 未记录"
    for entry in trace:
        assert {"index", "name", "kind"} <= set(entry)
        assert isinstance(entry["extra_keys"], list)
        assert isinstance(entry["extra_added"], list)


def test_trace_index_is_execution_order() -> None:
    res = _run()
    idx = [t["index"] for t in res["trace"]]
    assert idx == sorted(idx)


def test_trace_covers_schedule_kinds() -> None:
    """默认 schedule 含 analyze + transform → 轨迹都应出现。"""
    res = _run()
    kinds = {t["kind"] for t in res["trace"]}
    assert "analyze" in kinds
    assert "transform" in kinds
