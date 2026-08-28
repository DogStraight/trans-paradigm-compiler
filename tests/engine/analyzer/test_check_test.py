"""tests/engine/analyzer/test_check_test.py — 注释驱动测试框架（ruleid:/ok:）。

Semgrep 式零代码测试：样例源文件内嵌 `// ruleid: X` / `// ok: X` 注释，
框架（analyzer/check_test.py）运行检查后断言命中集合。本测试验证：
    - parse_directives 解析（ruleid/ok/多规则/区间归属）
    - 端到端：样例文件（违反/合规命名）→ 断言命中/未命中
    - 失败报告形态（ruleid 未命中 / ok 意外命中）
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.check_test import parse_directives, run_comment_driven  # noqa: E402
from analyzer.checker import ProjectChecker  # noqa: E402


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


class TestParseDirectives:
    def test_ruleid_and_ok(self):
        src = (
            "// ruleid: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n"
            "// ok: NC005\n"
            "module good;\n"
            "endmodule\n"
        )
        directives, region = parse_directives(src)
        assert len(directives) == 2
        assert directives[0] == {"line": 0, "type": "ruleid", "rules": ["NC001"]}
        assert directives[1] == {"line": 3, "type": "ok", "rules": ["NC005"]}
        # 区间：第一个指令到第二个指令前；第二个到 EOF
        assert region[0] == 3
        assert region[3] == len(src.splitlines())

    def test_multi_rules(self):
        src = "// ruleid: NC001, NC005\nmodule M;\nendmodule\n"
        directives, _ = parse_directives(src)
        assert directives[0]["rules"] == ["NC001", "NC005"]

    def test_no_directives(self):
        assert parse_directives("module m;\nendmodule\n") == ([], {})


class TestRunCommentDriven:
    """run_comment_driven 端到端（ruleid 命中/未命中、ok 反例）。"""

    def test_ruleid_hit(self, checker, tmp_path):
        """ruleid 标记的代码段命中 → 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ruleid_miss(self, checker, tmp_path):
        """ruleid 标记的代码段未命中 → 失败报告。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module good;\n"  # 合规命名，NC001 不命中
            "endmodule\n",
            encoding="utf-8",
        )
        failures = run_comment_driven(checker, str(p))
        assert len(failures) == 1
        assert "ruleid NC001 未命中" in failures[0]

    def test_ok_pass(self, checker, tmp_path):
        """ok 标记的代码段未命中 → 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ok: NC001\n"
            "module good;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ok_fail(self, checker, tmp_path):
        """ok 标记的代码段意外命中 → 失败报告。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ok: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        failures = run_comment_driven(checker, str(p))
        assert len(failures) == 1
        assert "ok NC001 意外命中" in failures[0]

    def test_multiple_regions(self, checker, tmp_path):
        """多段：ruleid（命中）+ ok（未命中）→ 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n"
            "// ok: NC005\n"
            "module good;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ruleid_same_line(self, checker, tmp_path):
        """指令与代码同行（模块声明行）→ 诊断计入该段。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "module Mux2x1; // ruleid: NC001\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []


class TestCrossFileNaming:
    """NC011 跨文件命名检查（模块名-文件名一致性，handler 兜底）。"""

    @pytest.fixture(scope="class")
    def checker(self):
        return ProjectChecker(rules_dir="grammar/verilog")

    def _check(self, checker, tmp_path, fname, src):
        p = tmp_path / fname
        p.write_text(src, encoding="utf-8")
        report = checker.check(str(p))
        codes = [
            d["code"]
            for f in report["files"]
            for d in f["semantic"]
        ]
        return codes

    def test_filename_mismatch_nc011(self, checker, tmp_path):
        """文件名与模块名不一致 → NC011。"""
        codes = self._check(
            checker, tmp_path, "adder.sv",
            "module Mux2x1;\nendmodule\n",
        )
        assert "NC011" in codes

    def test_filename_match_clean(self, checker, tmp_path):
        """文件名与模块名一致 → 无 NC011。"""
        codes = self._check(
            checker, tmp_path, "top.sv",
            "module top;\nendmodule\n",
        )
        assert "NC011" not in codes

    def test_multi_module_same_file(self, checker, tmp_path):
        """多模块同文件：任一模块匹配文件名 → 其余不误报。"""
        codes = self._check(
            checker, tmp_path, "top.sv",
            "module top;\nendmodule\n"
            "module helper;\nendmodule\n",
        )
        assert "NC011" not in codes

    def test_all_mismatch_reports_each(self, checker, tmp_path):
        """全部模块都与文件名不一致 → 每个都报。"""
        codes = self._check(
            checker, tmp_path, "core.sv",
            "module alpha;\nendmodule\n"
            "module beta;\nendmodule\n",
        )
        assert codes.count("NC011") == 2
    def test_ruleid_hit(self, checker, tmp_path):
        """ruleid 标记的代码段命中 → 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ruleid_miss(self, checker, tmp_path):
        """ruleid 标记的代码段未命中 → 失败报告。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module good;\n"  # 合规命名，NC001 不命中
            "endmodule\n",
            encoding="utf-8",
        )
        failures = run_comment_driven(checker, str(p))
        assert len(failures) == 1
        assert "ruleid NC001 未命中" in failures[0]

    def test_ok_pass(self, checker, tmp_path):
        """ok 标记的代码段未命中 → 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ok: NC001\n"
            "module good;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ok_fail(self, checker, tmp_path):
        """ok 标记的代码段意外命中 → 失败报告。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ok: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        failures = run_comment_driven(checker, str(p))
        assert len(failures) == 1
        assert "ok NC001 意外命中" in failures[0]

    def test_multiple_regions(self, checker, tmp_path):
        """多段：ruleid（命中）+ ok（未命中）→ 零失败。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "// ruleid: NC001\n"
            "module Mux2x1;\n"
            "endmodule\n"
            "// ok: NC005\n"
            "module good;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []

    def test_ruleid_same_line(self, checker, tmp_path):
        """指令与代码同行（模块声明行）→ 诊断计入该段。"""
        p = tmp_path / "sample.sv"
        p.write_text(
            "module Mux2x1; // ruleid: NC001\n"
            "endmodule\n",
            encoding="utf-8",
        )
        assert run_comment_driven(checker, str(p)) == []
