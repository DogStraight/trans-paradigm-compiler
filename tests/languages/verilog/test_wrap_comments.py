"""formatter 超长注释折行回归测试（VeriGood wrapComment 借鉴）。

验证：
  - 纯 `//` 超长注释按词折到 max_width，续行保留 `// ` 前缀
  - 行内注释（`code // comment`）不折
  - 幂等
  - 配置默认关闭（不改变现有输出）
"""

import pytest

from grammar.verilog.plugins.formatter.passes.wrap_comments import (
    run_wrap_comments,
    _wrap_comment_line,
)
from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

pytestmark = pytest.mark.usefixtures("config_loaded")


class TestWrapComments:
    def test_long_comment_wrapped(self):
        """纯 `//` 超长注释折成多行，全 ≤100。"""
        line = "// " + "word " * 40
        line = line.rstrip()
        out = run_wrap_comments([line], 100)
        assert len(out) >= 2
        for l in out:
            assert len(l) <= 100, f"折后应 ≤100: len={len(l)}"
            assert l.startswith("// "), "续行保留 // 前缀"

    def test_inline_comment_not_wrapped(self):
        """行内注释（代码 + //）不折。"""
        line = "    wire a; // " + "word " * 40
        line = line.rstrip()
        out = run_wrap_comments([line], 100)
        assert len(out) == 1, "行内注释不折"

    def test_idempotent(self):
        """折行二次稳定。"""
        line = "// " + "word " * 40
        line = line.rstrip()
        once = run_wrap_comments([line], 100)
        twice = run_wrap_comments(once, 100)
        assert twice == once

    def test_short_comment_untouched(self):
        """短注释不折（原样）。"""
        line = "// short comment"
        out = run_wrap_comments([line], 100)
        assert out == [line]

    def test_config_default_disabled(self):
        """配置默认关闭：format_source 不折注释（破坏性最小）。"""
        src = (
            "module m;\n"
            "    // " + "word " * 40 + "\n"
            "    wire a;\n"
            "endmodule\n"
        )
        out = format_source(src, DEFAULT_RULES_DIR)
        # 默认不启用 wrap_comments → 注释保持单行
        assert len([l for l in out.split("\n") if l.lstrip().startswith("//")]) == 1
