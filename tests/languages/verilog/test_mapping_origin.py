"""tests/languages/verilog/test_mapping_origin.py — 映射表来源追踪（0.1.2 阶段 6 可视化）。

回答"`type_ports_flat["spi"]["slave"]` 的行从哪来"（ADR-0015 §2）：
    展开侧（`_expand_ports`）写行 `origin`（展开链 + 源端口名）→
    SemanticMappingPlugin 旁路收集 → 插件 `describe()` →
    trace 条目 `artifacts` → `symbols/trace.json`。

断言的是**来源可解释**（链路形态），非具体表的业务值。
"""

import json

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = [pytest.mark.smoke, pytest.mark.usefixtures("config_loaded")]

INVERT_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : invert master;
}
"""

NESTED_SRC = """module top(
    input clk,
    wrap.slave w_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}

type wrap {
    master : spi.master inner, input enable;
    slave  : spi.slave inner;
}
"""

NESTED_INVERT_SRC = """module top(
    input clk,
    wrap.slave w_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}

type wrap {
    master : spi.master inner, input enable;
    slave  : invert master;
}
"""


def _run(src: str, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def _mapping_artifacts(trace: list[dict]) -> dict:
    """trace 中所有 transform 单元的插件自述合并。

    单元可拆为多个时点（插件级单元），故按**插件名**聚合而不取单条。
    """
    merged: dict = {}
    for entry in trace:
        if entry.get("kind") == "transform":
            merged.update(entry.get("artifacts", {}))
    return merged


def _table_sources(res: dict, table: str = "type_ports_flat") -> dict:
    """取 trace 中 transform 单元的映射表来源（无则失败）。"""
    art = _mapping_artifacts(res.get("trace", []))
    assert "SemanticMappingPlugin" in art, f"无插件自述: {art}"
    table_info = art["SemanticMappingPlugin"].get(table)
    assert table_info is not None, f"无 {table} 表自述: {art}"
    return table_info


def test_invert_rows_carry_expansion_chain():
    """纯 invert 展开：每行来源 = 起点角色 > invert(目标) > #端口名。"""
    r = _run(INVERT_SRC)
    assert r["success"], r.get("error", "")
    info = _table_sources(r)
    assert set(info["sources"]) == {"spi.master", "spi.slave"}
    slave = {row["name"]: row["origin"] for row in info["sources"]["spi.slave"]}
    assert slave["clk"] == "spi.slave > invert(spi.master) > #clk"
    assert slave["mosi"] == "spi.slave > invert(spi.master) > #mosi"
    master = {row["name"]: row["origin"] for row in info["sources"]["spi.master"]}
    assert master["clk"] == "spi.master > #clk"


def test_nested_rows_carry_nested_and_rename_segments():
    """嵌套展开：来源含 nested(实例:类型.角色) 与 rename(实例前缀) 段。"""
    r = _run(NESTED_SRC)
    assert r["success"], r.get("error", "")
    info = _table_sources(r)
    rows = {row["name"]: row["origin"] for row in info["sources"]["wrap.master"]}
    assert rows["inner_clk"] == (
        "wrap.master > nested(inner:spi.master) > rename(inner) > #clk"
    )
    # 表行数 = 各来源键的行数之和（所有 role 行都带来源时）
    assert info["rows"] == sum(len(v) for v in info["sources"].values())


def test_nested_invert_rows_carry_opposite_segment():
    """invert 含嵌套：嵌套段标 opposite(...)（取对侧展开）。"""
    r = _run(NESTED_INVERT_SRC)
    assert r["success"], r.get("error", "")
    info = _table_sources(r)
    origins = [row["origin"] for row in info["sources"]["wrap.slave"]]
    assert origins, "wrap.slave 无来源"
    nested_rows = [o for o in origins if "inner" in o]
    assert nested_rows, f"缺嵌套行来源: {origins}"
    assert all(
        o.startswith("wrap.slave > invert(wrap.master) > opposite(inner:")
        for o in nested_rows
    )


def test_trace_json_dumps_artifacts(tmp_path):
    """dump 模式：来源随 trace 落 symbols/trace.json（可视化管道出口）。"""
    ref = tmp_path / "samples" / "normal" / "ref"
    ref.mkdir(parents=True)
    src_file = ref / "ref_origin.v"
    src_file.write_text(INVERT_SRC, encoding="utf-8")

    # 落盘位置由显式 out_dir 决定（不依赖 input_path 的语料布局嗅探）
    out_dir = tmp_path / "samples" / "normal"
    r = _run(INVERT_SRC, input_path=str(src_file), out_dir=str(out_dir))
    assert r["success"], r.get("error", "")

    trace_file = out_dir / "symbols" / "trace.json"
    assert trace_file.exists(), "trace.json 未落盘"
    data = json.loads(trace_file.read_text(encoding="utf-8"))
    art = _mapping_artifacts(data["trace"])
    sources = art.get("SemanticMappingPlugin", {}).get("type_ports_flat", {})
    assert sources.get("sources", {}).get("spi.slave"), f"artifacts 未落盘: {art}"
