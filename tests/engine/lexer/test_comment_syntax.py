"""注释语法读取（`lexer/comment_syntax.py`）——注释标点全部来自语言包声明。

引擎不认识 `//` / `/* */`：verilog 是 `//` + `/* */`，yaml 是 `#`（无块注释），
c4 是 `//` 与 `#`（都算行注释，无块注释）。本测试把"声明 → 归一结果"钉死，
防任何一处重新硬编码注释标点。
"""

from lexer.comment_syntax import load_comment_syntax


class TestDeclaredPunctuation:
    """各语言包的注释标点来自其 `[comment] pairs` 声明。"""

    def test_verilog_line_and_block(self) -> None:
        s = load_comment_syntax("grammar/verilog")
        assert s.block_pairs == (("/*", "*/"),)
        assert s.line_starts == ("//",)
        assert s.line_start == "//"
        assert (s.block_open, s.block_close) == ("/*", "*/")

    def test_yaml_hash_only(self) -> None:
        s = load_comment_syntax("grammar/yaml")
        assert s.line_starts == ("#",)
        assert s.block_pairs == (), "yaml 无块注释声明"
        assert s.block_open is None and s.block_close is None

    def test_c4_two_line_forms_no_block(self) -> None:
        """c4 的 `//` 与 `#` 都是行注释（上游 c4.c next()），无块注释。"""
        s = load_comment_syntax("grammar/c4")
        assert s.line_starts == ("//", "#")
        assert s.block_pairs == ()
        assert s.line_start == "//", "书写取首条声明的行注释标记"

    def test_cached_per_rules_dir(self) -> None:
        assert load_comment_syntax("grammar/verilog") is load_comment_syntax(
            "grammar/verilog"
        )
