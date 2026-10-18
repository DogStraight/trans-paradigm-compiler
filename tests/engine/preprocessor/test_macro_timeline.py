"""宏定义时间线（`preprocessor/macro_timeline.py`）与调用点事实回源过滤。

背景：展开器对**全文件用最终宏表**（历史近似），而 C 的宏可见性是顺序的
（§6.10.2）。实参个数检查若按最终宏表判，会在"后置定义 / 重定义 / undef"上给出
与 C 不一致的结论。故 `scan_directives(out_macro_events=...)` 记录定义/取消事件，
`preprocessor._expand.map_invocations_to_source` 在回源原始行时：

  1. 丢弃 include 拼接内容行（`clean_to_raw` 为 None，别的文件坐标系）；
  2. 丢弃**行拼接段首**（行尾仍是 continuation 字符 ⇒ 行列不可靠）；
  3. 按时间线取调用点时点的可见形参表；当时不是函数宏 ⇒ 丢弃该调用点。

Doc: preprocessor/README.md（调用点事实） / preprocessor/macro_timeline.py
"""

from __future__ import annotations

from preprocessor import scan_directives
from preprocessor._expand import map_invocations_to_source
from preprocessor.macro_timeline import apply, params_at

PACK = "grammar/c"


# ── 事件表：扫描期记账 ─────────────────────────────────────


def _events(src: str) -> list[dict]:
    events: list[dict] = []
    scan_directives(src, PACK, out_macro_events=events)
    return events


def test_scan_records_define_and_undef_events() -> None:
    events = _events("#define F(a, b) a + b\n#undef F\n")
    assert events == [
        {"line": 1, "name": "F", "params": ["a", "b"]},
        {"line": 2, "name": "F", "params": None},
    ]


def test_scan_records_object_like_as_non_function() -> None:
    events = _events("#define N 4\n")
    assert events == [{"line": 1, "name": "N", "params": None}]


def test_scan_records_continuation_define_at_segment_start() -> None:
    """`#define` 续行合并：事件行 = 段首物理行（1-based）。"""
    events = _events("#define F(a, \\\n         b) a + b\n")
    assert events[0]["line"] == 1
    assert events[0]["params"] == ["a", "b"]


def test_scan_records_include_snapshot_at_include_line(tmp_path) -> None:
    """被包含文件的定义按 include 行处**一次快照**并入宿主时间线。"""
    (tmp_path / "h.h").write_text("#define F(a, b) a + b\n", encoding="utf-8")
    src = '#include "h.h"\n'
    events: list[dict] = []
    scan_directives(src, PACK, source_path=str(tmp_path / "s.c"),
                    search_dirs=[str(tmp_path)], out_macro_events=events)
    assert events == [{"line": 1, "name": "F", "params": ["a", "b"]}]


def test_inactive_branch_define_not_recorded() -> None:
    assert _events("#if 0\n#define F(a, b) a + b\n#endif\n") == []


# ── params_at / apply ─────────────────────────────────────


EVENTS = [
    {"line": 1, "name": "F", "params": ["a"]},
    {"line": 5, "name": "F", "params": None},
    {"line": 8, "name": "F", "params": ["a", "b"]},
    {"line": 3, "name": "G", "params": []},
]


def test_params_at_uses_latest_event_not_later_than_line() -> None:
    assert params_at(EVENTS, 2, "F") == ["a"]
    assert params_at(EVENTS, 4, "F") == ["a"]
    assert params_at(EVENTS, 6, "F") is None  # undef 后
    assert params_at(EVENTS, 9, "F") == ["a", "b"]  # 重定义后
    assert params_at(EVENTS, 0, "F") is None  # 定义前


def test_params_at_distinguishes_zero_params_from_undefined() -> None:
    assert params_at(EVENTS, 3, "G") == []  # 零形参函数宏
    assert params_at(EVENTS, 3, "H") is None  # 从未定义


def test_apply_overrides_params_and_drops_non_function_points() -> None:
    inv = [
        {"name": "F", "slots": 1, "params": ["latest"], "line": 2},
        {"name": "F", "slots": 1, "params": ["latest"], "line": 6},
        {"name": "F", "slots": 2, "params": ["latest"], "line": 9},
    ]
    apply(inv, EVENTS)
    assert [(i["line"], i["params"]) for i in inv] == [
        (2, ["a"]),
        (9, ["a", "b"]),
    ]


def test_apply_without_events_keeps_snapshot() -> None:
    inv = [{"name": "F", "slots": 1, "params": ["latest"], "line": 2}]
    apply(inv, None)
    assert inv[0]["params"] == ["latest"]


# ── map_invocations_to_source（回源 + 过滤）──────────────────


def _inv(name: str, line: int, params: list[str] | None = None) -> dict:
    return {
        "name": name,
        "slots": 1,
        "single_empty": False,
        "params": list(params or ["snapshot"]),
        "line": line,
        "column": 8,
    }


def test_map_clean_line_to_raw_line() -> None:
    inv = [_inv("F", 3)]
    map_invocations_to_source(inv, [1, None, 7], "a\nb\nc\nd\ne\nf\ng\n", None)
    assert [(i["line"], i["params"]) for i in inv] == [(7, ["snapshot"])]


def test_map_drops_unmappable_include_content_lines() -> None:
    inv = [_inv("F", 2)]
    map_invocations_to_source(inv, [1, None], "a\nb\n", None)
    assert inv == []


def test_map_drops_continuation_segment_lines() -> None:
    """原始行以 continuation 字符结尾 ⇒ 该行由多条物理行合并，位置不可靠。"""
    raw = "int a;\nint b = 1 + \\\n    2;\n"
    inv = [_inv("F", 2)]  # clean 第 2 行 → 原始第 2 行（续行段首）
    map_invocations_to_source(inv, [1, 2, 3], raw, None)
    assert inv == []


def test_map_applies_timeline_and_drops_non_function_points() -> None:
    raw = "int a;\nint b;\nint c;\nint d;\n"
    inv = [_inv("F", 1), _inv("F", 4)]  # 第 1 行：定义前；第 4 行：重定义后
    events = [
        {"line": 2, "name": "F", "params": ["a"]},
        {"line": 4, "name": "F", "params": ["a", "b"]},
    ]
    map_invocations_to_source(inv, [1, 2, 3, 4], raw, events)
    assert [(i["line"], i["params"]) for i in inv] == [(4, ["a", "b"])]
