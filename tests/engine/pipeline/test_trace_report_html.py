"""时点轨迹 HTML 报告（pipeline/report_html.py）渲染测试。

锁：单元卡片（name/kind/impl/黑板键）/ artifacts 通用值树渲染（dict → 表格、
list-of-dict → 带表头表格、深层 dict → 紧凑行）/ HTML 转义 / 空 trace 提示 /
执行管道条（单元链 + 产物流标签）/ 左轴节点 / 依赖行（requires 回指上游）。
"""

from pipeline.report_html import render_trace_html


def _entry(**kw) -> dict:
    base = {
        "index": 0,
        "name": "u0",
        "kind": "transform",
        "extra_added": [],
        "extra_keys": [],
    }
    base.update(kw)
    return base


def test_empty_trace_shows_hint() -> None:
    out = render_trace_html([])
    assert "0 units" in out
    assert "trace 为空" in out
    assert "<div class=\"file\">" not in out


def test_unit_card_fields() -> None:
    out = render_trace_html(
        [
            _entry(
                index=3,
                name="expand",
                kind="transform",
                impl="typed_ports.bridge",
                slot="build_wrapper",
                extra_added=["wrapper"],
                extra_keys=["wrapper", "scope"],
            )
        ]
    )
    assert "#3 expand" in out
    assert 'class="badge k-transform"' in out
    assert "typed_ports.bridge" in out
    assert "build_wrapper" in out
    assert "<code>wrapper</code>" in out
    assert "<code>scope</code>" in out


def test_kind_badges_counted() -> None:
    out = render_trace_html(
        [
            _entry(kind="analyze"),
            _entry(index=1, kind="transform"),
            _entry(index=2, kind="check"),
        ]
    )
    assert "3 units" in out
    assert "analyze ×1" in out and "transform ×1" in out and "check ×1" in out


def test_artifacts_generic_tree_rendering() -> None:
    """插件自述自由结构：dict → 表格；list-of-dict → 带表头表格；标量 → 值。"""
    out = render_trace_html(
        [
            _entry(
                artifacts={
                    "SlotRunner": {"slots_called": {"build_wrapper": 2}},
                    "Mapping": {
                        "type_ports_flat": {
                            "rows": 2,
                            "sources": {
                                "spi.slave": [
                                    {"name": "miso", "origin": "spi.slave > invert(spi.master) > #miso"}
                                ]
                            },
                        }
                    },
                }
            )
        ]
    )
    assert "SlotRunner" in out and "Mapping" in out
    assert "slots_called" in out and "build_wrapper" in out
    assert "<th>name</th>" in out and "<th>origin</th>" in out
    assert "spi.slave &gt; invert(spi.master) &gt; #miso" in out  # origin 链（转义后）
    assert "rows" in out


def test_html_escaped() -> None:
    out = render_trace_html(
        [
            _entry(
                name="<script>x</script>",
                impl='a"b',
                extra_added=["<img>"],
            )
        ]
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<img>" not in out


def test_source_path_shown() -> None:
    out = render_trace_html([], source_path="samples/x.v")
    assert "samples/x.v" in out


def test_uses_shared_report_css() -> None:
    """与 tpc check --html 同一视觉语言（共享样式常量，不重复维护）。"""
    from analyzer.report_html import REPORT_CSS

    out = render_trace_html([])
    assert REPORT_CSS[:40] in out
    assert ".badge" in out and ".file" in out


def test_pipe_chain_and_produced_labels() -> None:
    """顶部执行管道条：单元节点链（锚链到卡片）+ 箭头上标上游产物流。"""
    out = render_trace_html(
        [
            _entry(index=0, name="analyze", kind="analyze", produced=["scope"]),
            _entry(index=1, name="map", kind="transform", requires=["scope"]),
        ]
    )
    assert 'class="pipe"' in out
    assert 'href="#unit-0"' in out and 'href="#unit-1"' in out
    assert "<small>scope</small>" in out  # 箭头上游产物标签


def test_pipe_sub_timepoints_from_artifacts() -> None:
    """阶段内部链进管道条：analyze 的 postpass 链作**子时点**挂在节点下方。"""
    out = render_trace_html(
        [
            _entry(
                index=0,
                name="analyze",
                kind="analyze",
                produced=["scope"],
                artifacts={
                    "postpasses": [
                        {"name": "a.py:run", "diagnostics": 0},
                        {"name": "b.py:run", "diagnostics": 7},
                    ]
                },
            ),
            _entry(index=1, name="codegen", kind="transform"),
        ]
    )
    assert 'class="pipe-sub"' in out
    assert "postpass 链（子时点）" in out
    assert "#0.1 a.py:run" in out
    assert "#0.2 b.py:run" in out
    assert "+7" in out  # 诊断数只在本环节报过时标出


def test_pipe_no_sub_timepoints_without_chain() -> None:
    """无内部链的单元不产生子时点块（通用渲染，不假设谁有链）。"""
    out = render_trace_html([_entry(index=0, name="map", kind="transform")])
    assert 'class="pipe-sub"' not in out


def test_requires_linked_to_upstream_producer() -> None:
    """依赖行：requires 名机械回指上游产出该名的单元锚（名字等值匹配）。"""
    out = render_trace_html(
        [
            _entry(index=0, name="p", kind="transform", produced=["thing"]),
            _entry(index=1, name="c", kind="transform", requires=["thing"]),
        ]
    )
    assert (
        '依赖</td><td><a href="#unit-0">#0</a> <code>thing</code></td>' in out
    )


def test_requires_without_producer_renders_name_only() -> None:
    """requires 无上游产出记录（防御路径）→ 只显示名字，不做链接。"""
    out = render_trace_html([_entry(index=0, name="c", requires=["ghost"])])
    assert '<tr><td class="key">依赖</td><td><code>ghost</code></td></tr>' in out


def test_axis_nodes_carry_kind_color() -> None:
    """左轴：容器带轴样式；节点按 kind 着色；卡片带锚 id（管道条跳转目标）。"""
    out = render_trace_html([_entry(index=2, kind="check")])
    assert 'class="trace"' in out
    assert '<div class="tnode k-check"></div>' in out
    assert 'id="unit-2"' in out
