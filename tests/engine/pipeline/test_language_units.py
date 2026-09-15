"""语言包级加工单元声明（`tpc.toml [pipeline] units`）与契约数据路径。

0.1.2 建好的单元机制此前只有测试用过：声明只能放组件目录（编排寄生在插件上），
契约 `produces`/`requires` 只做校验——消费方实际靠"同 transformer 实例"拿产物
（`ConfigDrivenTransform` 扫兄弟插件）。本档锁定迁移后的三条保证：

1. 语言包根 `[pipeline] units` 与组件声明**两源合并**，同名 fail-fast；
2. 契约是**数据路径**：生产方 `note_produced` 发布 → 消费方按名取用（跨单元）；
3. 顺序违反 requires → fail-fast（配置错误不静默降级）。

Doc: pipeline/README.md（加工单元 / 契约校验）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")

TYPED_PORTS_SRC = """module top(
    input clk,
    spi.slave spi_io
);
endmodule

type spi {
    master : input clk, output [7:0] mosi, output cs;
    slave  : input clk, input [7:0] mosi, output cs;
}
"""


def _pack(tmp_path, body: str) -> str:
    """最小语言包目录（只放 tpc.toml——只测声明合并路径）。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tpc.toml").write_text(body, encoding="utf-8")
    return str(tmp_path)


def test_pack_units_read_and_ordered() -> None:
    """verilog 语言包根声明 4 个单元 → 显式时点序（analyze → slots → map → codegen）。"""
    from core.define import DEFAULT_RULES_DIR
    from pipeline import _resolve_language_units
    from pipeline.schedule import build_unit_schedule

    decls = _resolve_language_units(DEFAULT_RULES_DIR)
    assert list(decls) == ["analyze", "slots", "map", "codegen"]

    seq = build_unit_schedule(decls)
    assert seq is not None
    assert [(d.name, d.kind, d.impl) for d in seq] == [
        ("analyze", "analyze", "builtin.analyze"),
        ("slots", "transform", "slot_runner"),
        ("map", "transform", "SemanticMappingPlugin"),
        ("codegen", "transform", "ConfigDrivenTransform"),
    ]


def test_pack_unit_conflicting_with_component_fails_fast(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同名单元（语言包根 + 组件）→ fail-fast（时点编排按名引用，重名不明）。"""
    from pipeline import _resolve_language_units

    monkeypatch.setattr(
        "pipeline.get_pipeline_units",
        lambda: {"dup": {"type": "analyze", "impl": "builtin.analyze"}},
    )
    pack = _pack(
        tmp_path / "pack",
        '[[pipeline.units]]\nname = "dup"\ntype = "analyze"\nimpl = "builtin.analyze"\n',
    )
    with pytest.raises(ValueError, match="重复"):
        _resolve_language_units(pack)


def test_pack_unsupported_pipeline_key_fails_fast(tmp_path) -> None:
    """语言包根 `[pipeline]` 目前只支持 units——多出的键不静默忽略。"""
    from pipeline import _resolve_language_units

    pack = _pack(tmp_path / "pack", "[pipeline]\npasses = []\n")
    with pytest.raises(ValueError, match="只支持 units"):
        _resolve_language_units(pack)


def test_requires_violation_fails_fast() -> None:
    """消费方在无产物时执行 → fail-fast（声明了 requires 就必须被满足）。"""
    from pipeline.schedule import PassDecl, _check_contract

    decl = PassDecl(
        name="codegen",
        kind="transform",
        plugin="ConfigDrivenTransform",
        impl="ConfigDrivenTransform",
    )
    with pytest.raises(ValueError, match="requires 未满足"):
        _check_contract(decl, available=set())


def test_mapping_tables_flow_across_units() -> None:
    """契约数据路径：map 单元产出的映射表被 codegen 单元按名消费（跨单元）。

    旧实现靠"同 transformer 实例扫兄弟插件"——单元拆分后该路径断裂（实测
    展开全丢），故这条既是回归也是迁移的验收点。
    """
    r = run_pipeline_on_source(
        source=TYPED_PORTS_SRC, quiet=True, no_lint=True
    )
    assert r["success"], r.get("error", "")
    assert "spi_io_clk" in r["output"], r["output"]

    by_name = {e["name"]: e for e in r["trace"]}
    # map 与 codegen 各自独立时点，产物按契约名传递
    assert by_name["map"]["produced"] == ["mapping_tables"]
    assert "produced" not in by_name["codegen"] or not by_name["codegen"].get(
        "produced"
    )
