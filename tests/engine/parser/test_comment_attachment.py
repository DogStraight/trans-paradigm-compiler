"""注释 attachment 测试（ADR-0006 阶段 4 注释遍）。

parser 收集行尾注释时挂到节点 _attached_comments，renderer 用 line_suffix
原语锚定到语句行尾（Doc 一等公民），与 inline_comment.py 字符串级回插
双轨并存（restore 去重防重复）。
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
