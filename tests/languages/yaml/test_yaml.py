"""tests/languages/yaml/test_yaml.py — YAML 子集：缩进 token 机制验证。

迷你语言包验证 tpc 的缩进 token（space.indent/space.dedent）：
  1. lexer 按缩进网格生成 space.indent/space.dedent
  2. IndentBlock 规则用 space.indent/space.dedent 作为块边界（block_start/block_end）
  3. 多层嵌套 + 列表正确解析
  4. 渲染回 YAML 文本

yaml fixture / _parse / _node_names 见同目录 conftest.py。
流式集合/锚点/多文档的补全测试见 test_yaml_flow.py。
"""

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