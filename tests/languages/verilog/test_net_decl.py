"""tests/languages/verilog/test_net_decl.py — nettypes 插件声明语法（2005 全量批次 1）。

覆盖 grammar/verilog/plugins/nettypes/（A.2.1.3/A.2.2）：
    - 12 种 net_type 全谱声明（tri/triand/trior/tri0/tri1/trireg/uwire/
      wand/wor/supply0/supply1 + wire 扩展形态）
    - drive/charge strength、vectored/scalared、delay3（值/三值/mintypmax）
    - real/time/realtime 声明（模块体 + 过程体）
    - 幂等 + 渲染保真（strength/mintypmax 内容不丢）

插件开关语义（禁用 nettypes → 语法失效）由 tpc.toml enabled 列表控制，
本测试默认启用态（主配置）。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


NET_TYPES_SRC = """module m;
    tri bus;
    triand [7:0] ta, tb;
    trior to;
    tri0 t0;
    tri1 t1;
    trireg (small) tr;
    uwire uw;
    wand w1;
    wor w2;
    supply0 gnd;
    supply1 vcc;
    wire plain;
endmodule
"""


def test_net_type_spectrum_roundtrip():
    """12 种 net_type 全谱：parse 成功、渲染保真、幂等。"""
    r = _run(NET_TYPES_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for line in [
        "tri bus;",
        "triand [7:0] ta, tb;",
        "trior to;",
        "tri0 t0;",
        "tri1 t1;",
        "trireg (small) tr;",
        "uwire uw;",
        "wand w1;",
        "wor w2;",
        "supply0 gnd;",
        "supply1 vcc;",
        "wire plain;",
    ]:
        assert line in out, "缺少 %r:\n%s" % (line, out)
    assert r["idempotent"], "net 声明二次格式化漂移"


def test_drive_strength_roundtrip():
    """drive_strength 六种组合形态之一：渲染保真。"""
    src = "module m;\n    tri (strong0, pull1) a;\n    wand (weak0, highz1) [7:0] b = 8'h00;\n    wire (supply1, highz0) c;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "tri (strong0, pull1) a;" in out
    assert "wand (weak0, highz1) [7:0] b = 8'h00;" in out
    assert "wire (supply1, highz0) c;" in out
    assert r["idempotent"]


def test_charge_strength_only_trireg():
    """charge_strength 只配 trireg（语法层宽进，渲染保真）。"""
    src = "module m;\n    trireg (medium) a;\n    trireg (large) [3:0] b;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "trireg (medium) a;" in out
    assert "trireg (large) [3:0] b;" in out


def test_vectored_scalared_roundtrip():
    src = "module m;\n    tri vectored [15:0] v;\n    wand scalared signed [31:0] s;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "tri vectored [15:0] v;" in out
    assert "wand scalared signed [31:0] s;" in out
    assert r["idempotent"]


def test_delay3_forms_roundtrip():
    """delay3 三种形态：单值 / 三值 / mintypmax。"""
    src = (
        "module m;\n"
        "    wire #5 a;\n"
        "    tri #(1, 2, 3) b;\n"
        "    wire #(1:2:3) c;\n"
        "    wand #dparam d;\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "wire #5 a;" in out
    assert "tri #(1, 2, 3) b;" in out
    assert "wire #(1 : 2 : 3) c;" in out
    assert "wand #dparam d;" in out
    assert r["idempotent"]


def test_real_time_realtime_decl():
    """real/time/realtime 声明：模块体 + 过程体。"""
    src = (
        "module m;\n"
        "    real r1, r2 = 1.5;\n"
        "    realtime rt;\n"
        "    time t;\n"
        "    initial begin\n"
        "        real local_r = 2.5;\n"
        "        time local_t;\n"
        "    end\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "real r1, r2 = 1.5;" in out
    assert "realtime rt;" in out
    assert "time t;" in out
    assert "real local_r = 2.5;" in out
    assert "time local_t;" in out
    assert r["idempotent"]


def test_multidecl_with_strength_adjacent():
    """相邻声明行（普通 wire + 带 strength 的 wire）：column_align 不破坏
    strength 形态（回归：曾把 (strong1, pull0) 拆坏、非幂等）。"""
    src = "module m;\n    wire plain;\n    wire (strong1, pull0) driven;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "wire (strong1, pull0) driven;" in r["output"]
    assert r["idempotent"]
