"""行尾注释结构序渲染测试（ADR-0013 trailing 槽）。

parser 收集行尾注释时挂到节点 _comment_slots["trailing"]，renderer 用
LineSuffix 渲染锚定到语句行尾（Doc 一等公民）；restore 只处理 tpc
marker，普通注释不再字符串级回插（ADR-0013 目标④）。
"""

from pipeline import run_pipeline_on_source


def _run(src, **kw):
    kw.setdefault("rules_dir", "grammar/verilog")
    kw.setdefault("expand_macros", False)
    kw.setdefault("format_output", False)
    kw.setdefault("quiet", True)
    return run_pipeline_on_source(src, **kw)


class TestAttachment:
    def test_line_comment_attached_to_stmt(self):
        """行尾注释通过 attachment 锚定到语句行尾。"""
        src = "module m;\n    wire a; // wire a comment\n    assign x = a;\nendmodule\n"
        r = _run(src)
        assert r["success"]
        out = r.get("output", "")
        lines = [l for l in out.split("\n") if "wire a" in l]
        assert lines, "wire a 行应存在"
        assert "wire a comment" in lines[0]

    def test_multiple_comments(self):
        """多个语句各带注释，均锚定到各自行尾。"""
        src = (
            "module m;\n"
            "    wire a; // a comment\n"
            "    wire b; // b comment\n"
            "endmodule\n"
        )
        r = _run(src)
        out = r.get("output", "")
        lines = out.split("\n")
        a_line = next(l for l in lines if "wire a" in l and "a comment" in l)
        b_line = next(l for l in lines if "wire b" in l and "b comment" in l)
        assert a_line.endswith("// a comment")
        assert b_line.endswith("// b comment")

    def test_no_duplicate(self):
        """attachment + 锚点回插不重复（restore 去重）。"""
        src = "module m;\n    wire a; // only once\nendmodule\n"
        r = _run(src, format_output=True)
        out = r.get("output", "")
        assert out.count("only once") == 1

    def test_without_comment_no_change(self):
        """无注释源码输出不含注释噪音。"""
        src = "module m;\n    wire a;\nendmodule\n"
        r = _run(src)
        out = r.get("output", "")
        assert "//" not in out.replace("//  ", "")

    def test_attached_survives_analyze_transform(self):
        """attachment 穿过 analyze/transform 后仍渲染（下划线属性保留）。"""
        src = "module m;\n    wire a; // keep me\nendmodule\n"
        r = _run(src, analyzer_enabled=True, transform_enabled=True)
        assert r["success"]
        assert "keep me" in r.get("output", "")

    def test_midline_block_comment_stays_in_place(self):
        """行中块注释保持原位（P1.5）：`assign b = /* 嵌入 */ rst_n;` 的
        注释不得被 attachment 行尾化——应经锚点回插留在 `=` 与 `rst_n` 之间。"""
        src = (
            "module m;\n"
            "    assign b = /* 嵌入注释 */ rst_n;\n"
            "endmodule\n"
        )
        r = _run(src)
        assert r["success"]
        out = r.get("output", "")
        # 注释在 `rst_n` 之前（原位，`=` 后），而非语句行尾
        assert "/* 嵌入注释 */ rst_n" in out
        assert not out.rstrip().endswith("/* 嵌入注释 */")

    def test_midline_comment_not_attached(self):
        """行中注释不走 attachment/锚点通道——进 inline_after（token 标注定位）。"""
        from pipeline import run_pipeline_on_source

        src = "module m;\n    assign b = /* 嵌入 */ rst_n;\nendmodule\n"
        r = run_pipeline_on_source(
            source=src, rules_dir="grammar/verilog", quiet=True, no_lint=True,
        )
        parser = r.get("parser")
        # 锚点通道无此行中注释；inline_after（挂 AssignStmt，锚 "="）有
        if parser is not None:
            anchors = getattr(parser, "_comment_anchors", None) or []
            assert not any("嵌入" in a.get("text", "") for a in anchors), (
                "行中注释不应进锚点通道（inline_after 结构序渲染）"
            )
        # 渲染结果：注释在 `=` 与 `rst_n` 之间（原位）
        out = r.get("output", "")
        assert "/* 嵌入 */ rst_n" in out

    def test_block_body_comment_no_line_anchor_leftover(self):
        """block body 独立行注释收为 Comment 节点后，line 通道不残留冗余条目
        （ADR-0013 单机制：注释进树 = 结构序渲染，prepare_production 回溯
        曾重复吞进 _line_comment_anchors——restore existing_lines 本会跳过，
        条目纯冗余，collect 时清除）。"""
        src = (
            "module m;\n"
            "    always @(*) begin\n"
            "        // TOP comment\n"
            "        x = 1;\n"
            "    end\n"
            "    // module body comment\n"
            "    wire a;\n"
            "endmodule\n"
        )
        r = _run(src)
        assert r["success"]
        parser = r.get("parser")
        if parser is not None:
            la = getattr(parser, "_line_comment_anchors", None) or []
            assert not any("TOP comment" in a.get("text", "") for a in la), (
                "收为 Comment 节点的注释不应残留 line_anchor"
            )
            assert not any("module body comment" in a.get("text", "") for a in la)
        # 注释仍由 Comment 节点渲染（结构序，不丢）
        out = r.get("output", "")
        assert "TOP comment" in out
        assert "module body comment" in out


class TestAttachmentReal:
    def test_picorv32_no_regression(self):
        """PicoRV32 真实项目：attachment 后 8 module 全产出（保真度门禁）。"""
        import os

        ref = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "e2e", "samples", "real", "ref", "ref_picorv32.v",
        )
        with open(ref, encoding="utf-8") as f:
            src = f.read()
        r = _run(src, expand_macros=True)

        out = r.get("output", "")
        # 注意：缩进的 module（附件影响下不缩进）——断言结构完整
        assert r["success"]
        assert out.count("module ") >= 8
