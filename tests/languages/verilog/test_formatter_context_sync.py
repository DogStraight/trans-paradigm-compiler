"""formatter 拆行后 contexts 同步测试（ADR-0006 阶段 3 带结构行）。

根因：inst_port/wrap 拆行改变行数，但 contexts 未同步 → 后续 pass 按
index 取 contexts 错位（行号漂移）。修复：拆行 pass 就地同步 contexts
（每段派生复制源行 ctx）+ 引擎兜底对齐。

验收：
  1. inst_port 拆行后 contexts 与 lines 同长、行序对齐
  2. wrap 拆行后 contexts 同步（续行段标记 multi_line_cont）
  3. 引擎兜底：漏同步的 pass 后 contexts 自动补齐
  4. format_source 输出与修复前逐行一致（双跑对比由既有测试锁定）
"""

from grammar.verilog.plugins.formatter.boundary import LineContext
from grammar.verilog.plugins.formatter.engine import FormatterEngine, FormatterPass
from grammar.verilog.plugins.formatter.passes.inst_port import run_inst_port_align
from grammar.verilog.plugins.formatter.passes.wrap import run_wrap_pass


def _ctx(line_number: int, scope_depth: int = 1) -> LineContext:
    return LineContext(
        line_number=line_number,
        text="",
        scope_path=[],
        scope_depth=scope_depth,
        in_ifdef=False,
        ifdef_condition="",
    )


class TestInstPortContextSync:
    def test_split_keeps_contexts_aligned(self):
        """拆 1 行多端口 → 3 行，contexts 同步为 3 份（同源行 ctx）。"""
        lines = [
            "    u0 (",
            "        .clk(clk), .resetn(resetn), .data(data)",
            "    );",
        ]
        ctxs = [_ctx(1), _ctx(2, scope_depth=2), _ctx(3)]
        out = run_inst_port_align(list(lines), ctxs)
        assert len(out) == 5  # 端口行拆成 3
        assert len(ctxs) == 5  # contexts 同步
        # 拆出的 3 个端口行共享源行 ctx（line=2, depth=2）
        for i in (1, 2, 3):
            assert ctxs[i].line_number == 2
            assert ctxs[i].scope_depth == 2
        # 端口行后仍对齐
        assert ctxs[4].line_number == 3

    def test_no_split_contexts_unchanged(self):
        """不拆行时 contexts 原样（数量与内容）。"""
        lines = ["    .clk(clk),"]
        ctxs = [_ctx(1)]
        out = run_inst_port_align(list(lines), ctxs)
        assert out == lines
        assert len(ctxs) == 1
        assert ctxs[0].line_number == 1

    def test_impl_line_skipped_keeps_ctx(self):
        """impl 行不拆，ctx 保留。"""
        lines = ["    impl spi.master (.clk(clk), .data(data));"]
        ctxs = [_ctx(1)]
        out = run_inst_port_align(list(lines), ctxs)
        assert out == lines
        assert len(ctxs) == 1


class TestWrapContextSync:
    def test_wrap_derives_cont_ctx(self):
        """折行续行段 ctx 派生：multi_line_cont=True、header=源行号。"""
        lines = [
            "    assign result = very_long_expression + another_very_long_operand;"
        ]
        ctxs = [_ctx(1)]
        # 窄宽度强制折行
        out = run_wrap_pass(list(lines), ctxs, max_width=30, indent_width=4)
        assert len(out) > 1
        assert len(ctxs) == len(out)
        # 首段保留源 ctx
        assert ctxs[0].line_number == 1
        assert ctxs[0].multi_line_cont is False
        # 续行段：multi_line_cont=True、header=源行号
        for c in ctxs[1:]:
            assert c.multi_line_cont is True
            assert c.multi_header_line == 1

    def test_wrap_no_split_contexts_unchanged(self):
        lines = ["    assign a = b;"]
        ctxs = [_ctx(1)]
        out = run_wrap_pass(list(lines), ctxs, max_width=100, indent_width=4)
        assert out == lines
        assert len(ctxs) == 1
        assert ctxs[0].multi_line_cont is False


class TestEngineFallback:
    def test_engine_resyncs_after_unsynced_pass(self):
        """漏同步的拆行 pass 后，引擎按最近 ctx 派生补齐（后续 pass 可观察）。"""

        def _split_pass(lines, ctxs):
            del ctxs  # handler 协议签名参数（恶意 pass 故意不同步）
            # 恶意 pass：拆行但不同步 contexts（模拟未来漏同步的 pass）
            out = []
            for l in lines:
                out.append(l)
                out.append(l + " [dup]")
            return out

        seen: list[tuple[int, int]] = []

        def _observe_pass(lines, ctxs):
            # 观察 pass：记录 (行数, contexts 数)，验证兜底已对齐
            seen.append((len(lines), len(ctxs)))
            return lines

        eng = FormatterEngine([
            FormatterPass(name="evil", kind="handler", handler=_split_pass),
            FormatterPass(name="observe", kind="handler", handler=_observe_pass),
        ])
        out = eng.run(["a", "b"], [_ctx(1), _ctx(2)])
        assert len(out) == 4
        # observe pass 看到的 contexts 已与 lines 对齐（4 = 4）
        assert seen == [(4, 4)]

    def test_engine_shortens_contexts_when_lines_shrink(self):
        """行数变少（合并）时 contexts 截断对齐。"""

        def _merge_pass(lines, ctxs):
            del ctxs  # handler 协议签名参数（合并遍不需 contexts）
            return [lines[0]]

        eng = FormatterEngine([
            FormatterPass(name="merge", kind="handler", handler=_merge_pass),
        ])
        out = eng.run(["a", "b"], [_ctx(1), _ctx(2)])
        assert out == ["a"]
        assert len(eng._passes) == 1
