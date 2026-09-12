"""时点轨迹 HTML 报告（pipeline/report_html.py）渲染测试。

锁：单元卡片（name/kind/impl/黑板键）/ artifacts 通用值树渲染（dict → 表格、
list-of-dict → 带表头表格、深层 dict → 紧凑行）/ HTML 转义 / 空 trace 提示。
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
