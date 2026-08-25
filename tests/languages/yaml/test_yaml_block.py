"""tests/languages/yaml/test_yaml_block.py — YAML 块标量（| / >，indent_leq capture）。

对应 grammar/yaml/base/_token.toml 的 [[capture]] indent_leq mode：
  1. 触发条件：前一显著 token 是 ":" / "-"（值位置）+ 后随空白/指示符
     （after/next_chars 配置）——`a | b` 中缀不触发
  2. 内容捕获：指示符行 + 更深缩进的内容行（含空行），逐字保留
  3. 终止：非空行缩进 ≤ 触发行缩进；该行不消费，缩进机制继续工作
     （嵌套块内 dedent 正确）
  4. 渲染：原样输出（ref = token 内容），往返保真

yaml fixture / _parse / _node_names 见同目录 conftest.py。
"""

import pytest

from tests.languages.yaml.conftest import _parse, _node_names


class TestBlockScalarParse:
    def test_literal_block_value(self, yaml):
        """`key: |` → value 是 BlockScalar，后续条目正常。"""
        ast = _parse("key: |\n  line1\n  line2\nnext: 1\n", yaml)
        names = _node_names(ast)
        assert names == ["MappingEntry", "MappingEntry"]
        entry = ast.sub_node[0]
        assert entry.value.node_name == "BlockScalar"
        assert ast.sub_node[1].key.content == "next"

    def test_folded_block_value(self, yaml):
        ast = _parse("key: >\n  text\nnext: 1\n", yaml)
        assert ast.sub_node[0].value.node_name == "BlockScalar"

    def test_sequence_block_scalar(self, yaml):
        """`- |` → SequenceItem 的 value 是 BlockScalar。"""
        ast = _parse("- |\n  item text\n- next\n", yaml)
        items = ast.sub_node
        assert [i.node_name for i in items] == ["SequenceItem", "SequenceItem"]
        assert items[0].value.node_name == "BlockScalar"

    def test_nested_in_indent_block(self, yaml):
        """IndentBlock 内嵌套块标量（内容缩进更深）。"""
        ast = _parse(
            "key:\n    sub: |\n        text\n    other: 1\n",
            yaml,
        )
        entry = ast.sub_node[0]
        assert entry.value.node_name == "IndentBlock"
        inner = entry.value.sub_node
        assert inner[0].node_name == "MappingEntry"
        assert inner[0].value.node_name == "BlockScalar"
        assert inner[1].key.content == "other"

    def test_dedent_after_block(self, yaml):
        """块标量后反缩进到顶层：结构正确（缩进机制继续工作）。"""
        ast = _parse(
            "key:\n    sub: |\n        text\nnext: 1\n",
            yaml,
        )
        assert _node_names(ast) == ["MappingEntry", "MappingEntry"]
        assert ast.sub_node[1].key.content == "next"

    def test_chomping_indicator_verbatim(self, yaml):
        """切块指示（|+）原样保留（不做语义展开）。"""
        ast = _parse("key: |+\n  a\n\n  b\nnext: 1\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "BlockScalar"
        # token 内容含指示符与空行（token 节点 .value 是内容字符串）
        content = entry.value.value.value
        assert content.startswith("|+\n")

    def test_indent_indicator_verbatim(self, yaml):
        """缩进指示（|2）原样保留。"""
        ast = _parse("key: |2\n   two\nnext: 1\n", yaml)
        assert ast.sub_node[0].value.value.value.startswith("|2\n")

    def test_empty_block(self, yaml):
        """空块标量（指示符后立即是同级行）。"""
        ast = _parse("key: |\nnext: 1\n", yaml)
        assert ast.sub_node[0].value.node_name == "BlockScalar"


class TestBlockScalarRender:
    def test_literal_roundtrip(self, yaml):
        """渲染后往返再解析：结构与内容一致。"""
        src = "key: |\n  line1\n  line2\nnext: 1\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "key: |" in out
        assert "  line1" in out
        assert "  line2" in out
        assert "next: 1" in out
        # 往返
        ast2 = _parse(out, yaml)
        assert _node_names(ast2) == _node_names(ast)

    def test_sequence_roundtrip(self, yaml):
        src = "- |\n  text\n- next\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert _node_names(_parse(out, yaml)) == _node_names(ast)

    def test_blank_lines_preserved(self, yaml):
        src = "key: |+\n  a\n\n  b\nnext: 1\n"
        out = yaml["renderer"].render(_parse(src, yaml))
        assert "key: |+" in out
        assert "  a" in out
        assert "  b" in out


class TestBlockScalarTrigger:
    def test_infix_pipe_not_triggered(self, yaml):
        """`a | b`（值位置之外的中缀）不触发块标量——| 不是 YAML 符号，
        仍报词法错误（plain scalar 字符集缺口的既有行为，非块标量误吞）。"""
        with pytest.raises(ValueError, match="Unexpected token"):
            _parse("a | b\n", yaml)

    def test_pipe_glued_not_triggered(self, yaml):
        """`key: |x`（指示符直接粘内容）不触发（next_chars 排除）。"""
        with pytest.raises(ValueError, match="Unexpected token"):
            _parse("key: |x\n", yaml)
