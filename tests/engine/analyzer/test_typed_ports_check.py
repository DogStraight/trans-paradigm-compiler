"""test_typed_ports_check.py — typed_ports 增强语法语义检查（TP 族）。

组件内 postpass（_check.py）三族检查：
    A 表述完整：type/role 引用存在（TP001/TP002）、显式端口归属（TP003）、
      type 良构（role 端口不重复 TP004 / invert 悬空 TP002 / 自反 TP006）
    B 连接正确：interface_ref 未命中端口实例（TP010）、类型不匹配（TP011）、
      role 不同向（TP012）
    C 单驱动：同一接口实例被多个 impl 绑定 → TP020（多驱动预检，对齐
      展开后 W105）
pos/neg 各验证：坏输入被 TPxxx error 拦下（analyze 报错阻断展开）；好输入
零 TP 诊断。TP 诊断是 error 级 → ProjectChecker report semantic 阶段可观测。

正确写法基准 = ref_spi_inf 同向：模块端口 `type.role name`（接口实例）+
impl `type.role ... => name` **同 role**（impl 驱动同名 role 视角的线组）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker  # noqa: E402


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _tp_codes(report):
    """仅 TP 族诊断码（过滤 W001 等既有 warning）。"""
    return {
        d.get("code")
        for f in report["files"]
        for d in f["semantic"]
        if str(d.get("code", "")).startswith("TP")
    }


# ── 同向基线（ref_spi_inf 形态）────────────────────────


def _spi_master_impl() -> str:
    """`spi.master spi_io` 端口实例 + `impl spi.master => spi_io`（同向正确）。"""
    return (
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .mosi(data), .cs(cs_n)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n"
    )


def test_good_master_same_role_clean(checker, tmp_path):
    """同向 master：spi.master 实例 + impl spi.master → 零 TP。"""
    src = tmp_path / "t.sv"
    src.write_text(_spi_master_impl(), encoding="utf-8")
    report = checker.check(str(src))
    assert _tp_codes(report) == set()


def test_good_slave_same_role_clean(checker, tmp_path):
    """同向 slave：spi.slave 实例 + impl spi.slave → 零 TP。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.slave (.clk(clk), .mosi(data), .cs(cs_n)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert _tp_codes(report) == set()


# ── A：type/role 引用存在 ────────────────────────────


def test_impl_ref_missing_type(checker, tmp_path):
    """impl 引用不存在的 type → TP001。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl nosuch.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP001" in _tp_codes(report)


def test_impl_ref_missing_role(checker, tmp_path):
    """impl 引用 type 存在但 role 不存在 → TP002。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.bogus (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP002" in _tp_codes(report)


def test_typed_port_ref_missing_type(checker, tmp_path):
    """端口实例引用不存在的 type → TP001。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    nosuch.master spi_io\n"
        ");\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP001" in _tp_codes(report)


def test_typed_port_ref_missing_role(checker, tmp_path):
    """端口实例引用 type 存在但 role 不存在 → TP002。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.bogus spi_io\n"
        ");\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP002" in _tp_codes(report)


# ── A：显式端口名归属 ────────────────────────────────


def test_impl_typo_port_reported(checker, tmp_path):
    """impl 显式连接 typo 端口（不在 role 定义端口集）→ TP003。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .mosi_typo(data)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP003" in _tp_codes(report)


def test_impl_valid_ports_clean(checker, tmp_path):
    """impl 显式连接端口 ∈ 定义端口集 → 不报 TP003。"""
    src = tmp_path / "t.sv"
    src.write_text(_spi_master_impl(), encoding="utf-8")
    report = checker.check(str(src))
    assert "TP003" not in _tp_codes(report)


def test_impl_private_ports_binding_clean(checker, tmp_path):
    """impl 私有端口绑定（∉ role 集、∈ impl 定义块）→ 零 TP。

    ref_spi_inf 形态回归（fix f66a99c）：type 内 impl[master] 除 role 接口
    端口（miso/sck/mosi/cs）还带私有驱动端口（clk/rst_n）；模块级 `impl
    spi.master (.clk(clk), .rst_n(rst_n)) => spi_io` 连私有端口合法——TP003
    白名单 = role 端口 ∪ impl 定义端口。修复前私有端口被误当 typo 报 TP003
    → 阻断合法展开（run_all ref_spi_inf 展开空）。
    """
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    input rst_n,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .rst_n(rst_n)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input miso, output sck, mosi, cs;\n"
        "    slave  : invert master;\n"
        "    impl[master](\n"
        "        input clk,\n"
        "        input rst_n\n"
        "    ) {\n"
        "        wire q;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert _tp_codes(report) == set()


def test_impl_private_port_typo_still_reported(checker, tmp_path):
    """私有端口白名单只豁免 impl 定义端口；真 typo 仍报 TP003。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk), .mosi_typo(data)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input miso, output mosi, output cs;\n"
        "    slave  : invert master;\n"
        "    impl[master](\n"
        "        input clk\n"
        "    ) {\n"
        "        wire q;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    # .clk 是 impl 定义私有端口（豁免）；.mosi_typo 不在 role 也不在 impl
    # 定义端口集 → 仍按 typo 报 TP003（白名单加宽不漏真 typo）
    tp_codes = _tp_codes(report)
    assert "TP003" in tp_codes
    msgs = [
        d.get("message", "")
        for f in report["files"]
        for d in f["semantic"]
        if str(d.get("code", "")).startswith("TP")
    ]
    assert any("mosi_typo" in m for m in msgs), f"TP003 应指向 typo 端口 mosi_typo，实际: {msgs}"


# ── A：type 定义良构 ─────────────────────────────────


def test_role_duplicate_port_reported(checker, tmp_path):
    """同一 role 内端口名重复 → TP004。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, input clk;\n"
        "    slave  : input clk;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP004" in _tp_codes(report)


def test_invert_missing_role_reported(checker, tmp_path):
    """role 定义 invert 引用不存在的 role → TP002。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : invert nosuch;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP002" in _tp_codes(report)


def test_invert_self_reported(checker, tmp_path):
    """invert 自反引用自身 → TP006。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk;\n"
        "    slave  : invert slave;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP006" in _tp_codes(report)


# ── B：interface_ref 解析 + 类型匹配 + role 同向 ──────


def test_impl_ref_module_name_reported(checker, tmp_path):
    """impl `=> 模块名`（历史偏离错误写法）→ TP010。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => top;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi;\n"
        "    slave  : input clk, input mosi;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP010" in _tp_codes(report)


def test_impl_ref_unknown_name_reported(checker, tmp_path):
    """impl `=> 未声明名` → TP010。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => nosuch_inst;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi;\n"
        "    slave  : input clk, input mosi;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP010" in _tp_codes(report)


def test_impl_type_mismatch_reported(checker, tmp_path):
    """impl spi 绑定 sci 类型实例 → TP011（spi 端口不能连 sci）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl sci.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi;\n"
        "    slave  : input clk, input mosi;\n"
        "}\n"
        "\n"
        "type sci {\n"
        "    master : input clk, output tx;\n"
        "    slave  : input clk, input tx;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP011" in _tp_codes(report)


def test_impl_role_mismatch_reported(checker, tmp_path):
    """impl master 绑定 slave 实例 → TP012（role 不同向）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.slave spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi;\n"
        "    slave  : input clk, input mosi;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP012" in _tp_codes(report)


# ── C：单驱动（多 impl 绑定同一接口实例）──────────────


def test_multi_impl_same_instance_reported(checker, tmp_path):
    """同一接口实例被两个 impl 绑定 → TP020（多驱动预检）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "    impl spi.master (.clk(clk), .cs(cs_n)) => spi_io;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP020" in _tp_codes(report)


def test_single_impl_same_instance_clean(checker, tmp_path):
    """同一接口实例只被一个 impl 绑定 → 不报 TP020。"""
    src = tmp_path / "t.sv"
    src.write_text(_spi_master_impl(), encoding="utf-8")
    report = checker.check(str(src))
    assert "TP020" not in _tp_codes(report)


def test_multi_impl_distinct_instances_clean(checker, tmp_path):
    """两个 impl 绑两个不同实例（每组线单驱动）→ 不报 TP020。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module top(\n"
        "    input clk,\n"
        "    spi.master spi_io,\n"
        "    spi.master spi_io2\n"
        ");\n"
        "    impl spi.master (.clk(clk)) => spi_io;\n"
        "    impl spi.master (.clk(clk), .cs(cs_n)) => spi_io2;\n"
        "endmodule\n"
        "\n"
        "type spi {\n"
        "    master : input clk, output mosi, output cs;\n"
        "    slave  : input clk, input mosi, output cs;\n"
        "}\n",
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert "TP020" not in _tp_codes(report)
