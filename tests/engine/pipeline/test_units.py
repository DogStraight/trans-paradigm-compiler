"""加工单元实例 + 统一时点生成（0.1.2 阶段 5a，ADR-0015 §1）。

覆盖：显式配置品类解析（type/impl/after|order/params，fail-fast）、时点统一生成
（声明序填空 / order 钉号 / after 推导 / 多实例同 impl）、诊断（冲突 / 环 / 未知引用）。
"""
import pytest

from pipeline.units import UnitInstance, assign_points, parse_units

pytestmark = pytest.mark.smoke


def _u(name: str, **kw) -> UnitInstance:
    base = {"type": "transform", "impl": f"impl_{name}"}
    base.update(kw)
    return UnitInstance(name=name, **base)


class TestParseUnits:
    def test_valid_explicit_format(self) -> None:
        units = parse_units(
            {
                "a": {"type": "analyze", "impl": "x.y", "params": {"k": 1}},
                "b": {"type": "transform", "impl": "p.q", "after": "a"},
            }
        )
        assert [u.name for u in units] == ["a", "b"]
        assert units[0].params == {"k": 1}
        assert units[1].after == "a"

    def test_bad_type(self) -> None:
        with pytest.raises(ValueError, match="type 非法"):
            parse_units({"a": {"type": "nope", "impl": "x"}})

    def test_missing_impl(self) -> None:
        with pytest.raises(ValueError, match="缺 impl"):
            parse_units({"a": {"type": "analyze"}})

    def test_order_after_mutex(self) -> None:
        with pytest.raises(ValueError, match="互斥"):
            parse_units(
                {"a": {"type": "analyze", "impl": "x", "after": "b", "order": 1}}
            )

    def test_bad_order(self) -> None:
        with pytest.raises(ValueError, match="非负整数"):
            parse_units({"a": {"type": "analyze", "impl": "x", "order": -1}})

    def test_not_table(self) -> None:
        with pytest.raises(ValueError, match="须为表"):
            parse_units({"a": "x"})  # type: ignore[dict-item]


class TestAssignPoints:
    def test_declaration_order_fill(self) -> None:
        out = assign_points([_u("a"), _u("b"), _u("c")])
        assert [(u.name, u.point) for u in out] == [("a", 0), ("b", 1), ("c", 2)]

    def test_explicit_order_pins(self) -> None:
        out = assign_points([_u("a", order=5), _u("b")])
        assert {u.name: u.point for u in out} == {"a": 5, "b": 0}
        assert [u.name for u in out] == ["b", "a"]  # 返回按点序

    def test_after_chain(self) -> None:
        out = assign_points([_u("a"), _u("b", after="a"), _u("c", after="b")])
        assert {u.name: u.point for u in out} == {"a": 0, "b": 1, "c": 2}

    def test_after_declared_before_target(self) -> None:
        """after 指向后声明的单元：after 条目等目标解析后才落点（target+1），
        无约束条目按声明序填空——故 a 落 0、b 落 1。"""
        out = assign_points([_u("b", after="a"), _u("a")])
        assert {u.name: u.point for u in out} == {"a": 0, "b": 1}

    def test_multi_instance_same_impl(self) -> None:
        """同一变换多实例（不同时点/参数）——显式配置品类的核心用例。"""
        out = assign_points(
            [
                _u("tp_expand", impl="typed_ports.slot"),
                _u(
                    "tp_check",
                    after="tp_expand",
                    impl="typed_ports.slot",
                    params={"mode": "check"},
                ),
            ]
        )
        assert {u.name: u.point for u in out} == {"tp_expand": 0, "tp_check": 1}
        assert out[0].impl == out[1].impl
        assert out[1].params == {"mode": "check"}

    def test_conflict_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="已被占用"):
            assign_points([_u("a", order=1), _u("b", order=1)])

    def test_cycle_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="环|不可达"):
            assign_points([_u("a", after="b"), _u("b", after="a")])

    def test_unknown_ref_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="未声明单元"):
            assign_points([_u("a", after="zz")])


class TestDeclarationLoading:
    """插件 `[pipeline] units` 声明加载（显式 + 带参数的配置品类）。"""

    def test_load_units_from_plugin_decl(self) -> None:
        from core.plugin_loader import _load_pipeline_decls

        out = _load_pipeline_decls(
            "/tmp",
            {
                "units": [
                    {"name": "u1", "type": "analyze", "impl": "a.b", "params": {"k": 1}}
                ]
            },
        )
        assert out["units"] == {
            "u1": {"type": "analyze", "impl": "a.b", "params": {"k": 1}}
        }

    def test_load_units_missing_name(self) -> None:
        from core.plugin_loader import _load_pipeline_decls

        with pytest.raises(ValueError, match="缺 name"):
            _load_pipeline_decls("/tmp", {"units": [{"type": "analyze"}]})

    def test_load_units_not_table(self) -> None:
        from core.plugin_loader import _load_pipeline_decls

        with pytest.raises(ValueError, match="须为表"):
            _load_pipeline_decls("/tmp", {"units": ["x"]})  # type: ignore[list-item]


class TestBuildSequence:
    """声明 → 有序单元序列（时点由调度器统一生成）。"""

    def test_build_from_decl(self) -> None:
        from pipeline.units import build_unit_sequence

        seq = build_unit_sequence(
            {
                "a": {"type": "analyze", "impl": "builtin.analyze"},
                "b": {"type": "transform", "impl": "builtin.transform", "after": "a"},
            }
        )
        assert [(u.name, u.point) for u in seq] == [("a", 0), ("b", 1)]

    def test_build_empty(self) -> None:
        from pipeline.units import build_unit_sequence

        assert build_unit_sequence(None) == []
        assert build_unit_sequence({}) == []
