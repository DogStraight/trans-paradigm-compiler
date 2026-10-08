"""tests/languages/yaml/test_yaml.py — YAML 子集：缩进 token 机制验证。

迷你语言包验证 tpc 的缩进 token（space.indent/space.dedent）：
  1. lexer 按缩进网格生成 space.indent/space.dedent
  2. IndentBlock 规则用 space.indent/space.dedent 作为块边界（block_start/block_end）
  3. 多层嵌套 + 列表正确解析
  4. 渲染回 YAML 文本

yaml fixture / _parse / _node_names 见同目录 conftest.py。
流式集合/锚点/多文档的补全测试见 test_yaml_flow.py。
"""

from core.token_protocol import TRIVIA_TOKEN_TYPES
from tests.languages.yaml.conftest import _parse, _node_names


class TestIndentTokens:
    """lexer 缩进 token 生成。"""

    def test_flat_mapping_no_indent_tokens(self, yaml):
        """无缩进的映射：不产生 space.indent/space.dedent。"""
        tokens = yaml["lexer"].tokenize("host: localhost\n")
        types = [t.type for t in tokens]
        assert "space.indent" not in types
        assert "space.dedent" not in types

    def test_nested_mapping_emits_indent(self, yaml):
        """嵌套映射：产生 space.indent。"""
        tokens = yaml["lexer"].tokenize("server:\n    host: localhost\n")
        types = [t.type for t in tokens]
        assert "space.indent" in types

    def test_dedent_emitted_on_unindent(self, yaml):
        """反缩进：产生 space.dedent。"""
        tokens = yaml["lexer"].tokenize(
            "server:\n    host: localhost\nother: 1\n"
        )
        types = [t.type for t in tokens]
        assert "space.dedent" in types


class TestParse:
    """YAML 子集解析。"""

    def test_flat_mapping(self, yaml):
        """单层映射。"""
        ast = _parse("host: localhost\nport: 8080\n", yaml)
        names = _node_names(ast)
        assert names == ["MappingEntry", "MappingEntry"]

    def test_nested_mapping_block(self, yaml):
        """嵌套映射：缩进块挂在 MappingEntry 的 value 下。"""
        ast = _parse("server:\n    host: localhost\n", yaml)
        names = _node_names(ast)
        assert names == ["MappingEntry"]
        entry = ast.sub_node[0]
        assert entry.key.content == "server"
        assert entry.value.node_name == "IndentBlock"
        inner = entry.value.sub_node[0]
        assert inner.node_name == "MappingEntry"
        assert inner.key.content == "host"

    def test_multi_level_nesting(self, yaml):
        """多层嵌套（3 层缩进）。"""
        ast = _parse(
            "a:\n    b:\n        c: 1\n",
            yaml,
        )
        entry_a = ast.sub_node[0]
        assert entry_a.value.node_name == "IndentBlock"
        entry_b = entry_a.value.sub_node[0]
        assert entry_b.value.node_name == "IndentBlock"
        entry_c = entry_b.value.sub_node[0]
        assert entry_c.key.content == "c"

    def test_sequence_items(self, yaml):
        """列表项（- item）。"""
        ast = _parse("ports:\n    - 8080\n    - 9090\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "IndentBlock"
        items = entry.value.sub_node
        assert [i.node_name for i in items] == ["SequenceItem", "SequenceItem"]
        assert items[0].value.node_name == "Number"

    def test_scalar_types(self, yaml):
        """标量类型：标识符/数字/布尔/null。"""
        ast = _parse(
            "a: hello\nb: 42\nc: true\nd: null\n",
            yaml,
        )
        entries = ast.sub_node
        assert entries[0].value.node_name == "Identifier"
        assert entries[1].value.node_name == "Number"
        assert entries[2].value.node_name == "BoolLit"
        assert entries[3].value.node_name == "NullLit"

    def test_string_scalar(self, yaml):
        """引号字符串标量。"""
        ast = _parse('name: "hello"\n', yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "StringLit"

    def test_single_quote_string_scalar(self, yaml):
        """单引号字符串标量（[string] delimiters 含 '，delim capture mode）。"""
        ast = _parse("name: 'hello'\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "StringLit"


class TestSignedNumber:
    """负数形态（`[[number.based]] lead_sign`）：语义 + 显著 token 序列 + 序列指示符不回归。

    回归背景（2026-10-09，实测）：旧 `yaml_neg` 声明（`base_prefix = "-"`）**不可达**
    （lexer 只在数字字符上进入数字扫描，`-` 不触发任何入口）⇒
      · `key: -5` 被当块序列：`MappingEntry(空值)` + `SequenceItem`，渲染 `key: \\n- 5`（语义变）；
      · `list: [1, -2]` **整篇 parse 截断 → 渲染空串**（内容丢失，最严重的一档）。
    修在词法层（`lead_sign`：符号后至少一位数字才成 `literal.number`），
    故 `- 8080`（符号后有空格）仍是序列指示符（见下对照用例）。
    Doc: grammar/yaml/base/_number.toml、lexer/README.md（`[[number.based]]` 字段表）
    """

    @staticmethod
    def _sig(tokens) -> list[tuple[str, str]]:
        return [(t.type, t.content) for t in tokens if t.type not in TRIVIA_TOKEN_TYPES]

    def test_negative_scalar_is_single_number_token(self, yaml):
        """`-5` 整体一个 `literal.number`（符号与数字相邻 ⇒ 词法事实）。"""
        assert self._sig(yaml["lexer"].tokenize("key: -5\n")) == [
            ("literal.plain", "key"),
            ("symbol.base.colon", ":"),
            ("literal.number", "-5"),
        ]

    def test_negative_value_parses_as_number(self, yaml):
        ast = _parse("key: -5\n", yaml)
        assert _node_names(ast) == ["MappingEntry"]
        assert ast.sub_node[0].value.node_name == "Number"
        assert ast.sub_node[0].value.value.value == "-5"

    def test_negative_value_renders_adjacent(self, yaml):
        """验收①：渲染后 `-` 与 `5` 相邻，且显著 token 序列与源逐项相同。"""
        src = "key: -5\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "key: -5" in out
        assert "- 5" not in out
        assert self._sig(yaml["lexer"].tokenize(out)) == self._sig(
            yaml["lexer"].tokenize(src)
        )

    def test_negative_value_comment_kept(self, yaml):
        out = yaml["renderer"].render(_parse("key: -5  # c\n", yaml))
        assert "-5" in out
        assert "# c" in out

    def test_flow_seq_negative_renders(self, yaml):
        """验收②：`list: [1, -2]` 非空且 token 序列逐项相同（修前是空串）。"""
        src = "list: [1, -2]\n"
        ast = _parse(src, yaml)
        assert ast.sub_node[0].value.node_name == "FlowSeq"
        out = yaml["renderer"].render(ast)
        assert out.strip() == "list: [1, -2]"
        assert self._sig(yaml["lexer"].tokenize(out)) == self._sig(
            yaml["lexer"].tokenize(src)
        )

    def test_flow_map_negative_renders(self, yaml):
        out = yaml["renderer"].render(_parse("m: {x: -1}\n", yaml))
        assert out.strip() == "m: {x: -1}"

    def test_negative_sequence_item(self, yaml):
        ast = _parse("seq:\n- -5\n", yaml)
        assert _node_names(ast) == ["MappingEntry", "SequenceItem"]
        item = ast.sub_node[1]
        assert item.value.node_name == "Number"
        assert item.value.value.value == "-5"

    def test_sequence_indicator_not_regressed(self, yaml):
        """验收③：`- 8080`（符号后有空格）仍是序列指示符，不被吃成数字。"""
        ast = _parse("seq:\n- 8080\n", yaml)
        assert _node_names(ast) == ["MappingEntry", "SequenceItem"]
        assert ast.sub_node[1].value.node_name == "Number"
        assert ast.sub_node[1].value.value.value == "8080"  # 不含符号
        out = yaml["renderer"].render(ast)
        assert "- 8080" in out

    def test_render_is_idempotent(self, yaml):
        """渲染幂等：修前 `list: [1, -2]` 渲成空串、`key: -5` 语义变，二次渲染不稳。"""
        for src in ("key: -5\n", "list: [1, -2]\n", "m: {x: -1}\n", "seq:\n- -5\n"):
            ast = _parse(src, yaml)
            out = yaml["renderer"].render(ast)
            again = yaml["renderer"].render(_parse(out, yaml))
            assert again == out, f"{src!r} 渲染不幂等"


class TestRender:
    """渲染回 YAML 文本。"""

    def test_flat_mapping_renders(self, yaml):
        """单层映射渲染。"""
        ast = _parse("host: localhost\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "host: localhost" in out

    def test_nested_mapping_renders(self, yaml):
        """嵌套映射渲染（缩进块）。"""
        ast = _parse("server:\n    host: localhost\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "server:" in out
        assert "host: localhost" in out

    def test_sequence_renders(self, yaml):
        """列表项渲染。"""
        ast = _parse("ports:\n    - 8080\n    - 9090\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "- 8080" in out
        assert "- 9090" in out