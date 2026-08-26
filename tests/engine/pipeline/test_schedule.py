"""test_schedule.py — 编排管线（ADR-0007）单测。

覆盖：时点序列器（order/after/默认序）、冲突/环/未知名 fail-fast、
pass 声明校验、缺省 schedule 语义、多轮/自由排序。
"""

import pytest

from pipeline.schedule import (
    PassDecl,
    PassState,
    build_schedules,
    _sequence_entries,
    DEFAULT_SCHEDULE_NAME,
)


# ── 序列器纯逻辑 ──────────────────────────────────────────


class TestSequenceEntries:
    def test_declaration_order_default(self):
        names = _sequence_entries(
            ["a", "b", "c"], "s", {"a", "b", "c"}
        )
        assert names == ["a", "b", "c"]

    def test_explicit_order(self):
        names = _sequence_entries(
            ["a", {"name": "b", "order": 0}, "c"], "s", {"a", "b", "c"}
        )
        assert names == ["b", "a", "c"]

    def test_after_moves_later(self):
        names = _sequence_entries(
            [{"name": "a", "after": "c"}, "b", "c"], "s", {"a", "b", "c"}
        )
        assert names == ["b", "c", "a"]

    def test_after_chain(self):
        # a after b, b after c, c 默认首
        names = _sequence_entries(
            [{"name": "a", "after": "b"}, {"name": "b", "after": "c"}, "c"],
            "s",
            {"a", "b", "c"},
        )
        assert names == ["c", "b", "a"]

    def test_after_forward_reference(self):
        # after 引用声明在后的条目也成立
        names = _sequence_entries(
            [{"name": "a", "after": "b"}, "b"], "s", {"a", "b"}
        )
        assert names == ["b", "a"]

    def test_slot_conflict_fail_fast(self):
        with pytest.raises(ValueError, match="时点冲突"):
            _sequence_entries(
                [{"name": "a", "order": 0}, {"name": "b", "order": 0}],
                "s",
                {"a", "b"},
            )

    def test_order_vs_after_conflict(self):
        # b 显式 order=1；a after c 推导 slot 1（c 默认 slot 0）→ 冲突
        with pytest.raises(ValueError, match="时点冲突"):
            _sequence_entries(
                [
                    {"name": "a", "after": "c"},
                    {"name": "b", "order": 1},
                    "c",
                ],
                "s",
                {"a", "b", "c"},
            )

    def test_after_cycle_fail_fast(self):
        with pytest.raises(ValueError, match="环"):
            _sequence_entries(
                [
                    {"name": "a", "after": "b"},
                    {"name": "b", "after": "a"},
                ],
                "s",
                {"a", "b"},
            )

    def test_unknown_pass_fail_fast(self):
        with pytest.raises(ValueError, match="未声明"):
            _sequence_entries(["a", "nope"], "s", {"a", "b"})

    def test_duplicate_pass_fail_fast(self):
        with pytest.raises(ValueError, match="重复"):
            _sequence_entries(["a", "a"], "s", {"a"})

    def test_unknown_after_fail_fast(self):
        with pytest.raises(ValueError, match="after 引用未声明"):
            _sequence_entries(
                [{"name": "a", "after": "nope"}], "s", {"a"}
            )

    def test_order_after_mutual_exclusive(self):
        with pytest.raises(ValueError, match="互斥"):
            _sequence_entries(
                [{"name": "a", "order": 0, "after": "b"}], "s", {"a", "b"}
            )

    def test_negative_order_fail_fast(self):
        with pytest.raises(ValueError, match="非负整数"):
            _sequence_entries([{"name": "a", "order": -1}], "s", {"a"})


# ── 调度构建（含内置 + 插件声明） ──────────────────────────


class TestBuildSchedules:
    def test_default_schedule_without_declarations(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls", lambda: {}
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        scheds = build_schedules("dummy")
        assert set(scheds) == {DEFAULT_SCHEDULE_NAME}
        assert [p.name for p in scheds[DEFAULT_SCHEDULE_NAME]] == [
            "analyze",
            "transform",
        ]

    def test_default_analyze_transform_kind(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls", lambda: {}
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        scheds = build_schedules("dummy")
        decls = scheds[DEFAULT_SCHEDULE_NAME]
        assert [d.kind for d in decls] == ["analyze", "transform"]

    def test_transform_first_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls", lambda: {}
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules",
            lambda: {
                "transform_first": {
                    "name": "transform_first",
                    "passes": ["transform", "analyze"],
                }
            },
        )
        scheds = build_schedules("dummy")
        assert [d.name for d in scheds["transform_first"]] == [
            "transform",
            "analyze",
        ]
        # 未声明的 default 仍补默认行为
        assert [d.name for d in scheds[DEFAULT_SCHEDULE_NAME]] == [
            "analyze",
            "transform",
        ]

    def test_custom_pass_with_handler(self, monkeypatch):
        def fake_handler(state):
            del state

        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls",
            lambda: {
                "post_check": {
                    "name": "post_check",
                    "kind": "custom",
                    "_handler": fake_handler,
                }
            },
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules",
            lambda: {
                "check": {
                    "name": "check",
                    "passes": ["post_check", "analyze"],
                }
            },
        )
        scheds = build_schedules("dummy")
        decls = scheds["check"]
        assert decls[0].name == "post_check"
        assert decls[0].handler is fake_handler

    def test_custom_pass_without_handler_fail_fast(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls",
            lambda: {"bare": {"name": "bare", "kind": "custom"}},
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        with pytest.raises(ValueError, match="缺 handler"):
            build_schedules("dummy")

    def test_bad_kind_fail_fast(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls",
            lambda: {"weird": {"name": "weird", "kind": "banana"}},
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        with pytest.raises(ValueError, match="kind 非法"):
            build_schedules("dummy")

    def test_builtin_name_conflict_fail_fast(self, monkeypatch):
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls",
            lambda: {"analyze": {"name": "analyze", "kind": "custom"}},
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        with pytest.raises(ValueError, match="冲突"):
            build_schedules("dummy")

    def test_pass_name_inferred_kind_from_builtin(self, monkeypatch):
        # 自定义同名内置 kind 的 pass 会被拒；其他名字无 kind 声明报错
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_pass_decls",
            lambda: {"mystery": {"name": "mystery"}},
        )
        monkeypatch.setattr(
            "pipeline.schedule.get_pipeline_schedules", lambda: {}
        )
        with pytest.raises(ValueError, match="kind 非法"):
            build_schedules("dummy")


# ── PassState 数据总线 ─────────────────────────────────────


class TestPassState:
    def test_extra_channel_isolated(self):
        s1 = PassState(ast=None, scope=None, ctx=None)
        s2 = PassState(ast=None, scope=None, ctx=None)
        s1.extra["k"] = 1
        assert "k" not in s2.extra


# ── 管线级集成（缺省 schedule = 旧行为 / 开关过滤 / stage 截断） ──


class TestPipelineIntegration:
    """经 run_pipeline_on_source 验证调度执行（需完整语言包）。"""

    ENHANCED_SRC = """module top(
    input clk,
    spi.slave spi_io
);
    spi_master u0 (.clk(clk));
    impl spi.master (.clk(clk)) => top;
endmodule

type spi {
    master : input clk, input miso, output mosi, output cs;
    slave  : input clk, input mosi, output miso, output cs;
    impl [master] (
        input clk,
        output sck
    ) {
        wire [7:0] data;
    }
}
"""

    def test_default_schedule_runs_analyze_then_transform(self):
        """缺省 schedule [analyze, transform]：增强端口被展开（旧行为）。"""
        from pipeline import run_pipeline_on_source

        r = run_pipeline_on_source(
            source=self.ENHANCED_SRC, quiet=True, no_lint=True
        )
        assert r["success"], r.get("error", "")
        # 展开产物：spi.slave → 具体端口（transform 消费 analyze 的 scope）
        assert "spi_io_clk" in r["output"]

    def test_unknown_schedule_name_fail_fast(self):
        from pipeline import run_pipeline_on_source

        src = "module m;\n  assign out = in;\nendmodule\n"
        with pytest.raises(ValueError, match="未声明"):
            run_pipeline_on_source(src, quiet=True, schedule="nope")

    def test_stage_analyze_stops_after_analyze_pass(self):
        """stage=\"analyze\"：执行完名为 analyze 的 pass 后截断（无输出）。"""
        from pipeline import run_pipeline_on_source

        src = "module m;\n  assign out = in;\nendmodule\n"
        r = run_pipeline_on_source(src, quiet=True, stage="analyze")
        assert r["success"], r.get("error", "")
        assert r["ast"] is not None
        assert not r.get("output")

    def test_analyzer_disabled_filters_analyze_pass(self):
        """analyzer_enabled=False 滤掉 analyze：无 scope，transform 跳过。"""
        from pipeline import run_pipeline_on_source

        src = "module m;\n  assign out = in;\nendmodule\n"
        r = run_pipeline_on_source(
            source=src, quiet=True, analyzer_enabled=False
        )
        assert r["success"], r.get("error", "")
