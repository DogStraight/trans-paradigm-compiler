"""tests/languages/yaml/test_yaml_flow.py — YAML 子集补全：流式集合/锚点/多文档。

补全范围（对应 grammar/yaml/01_flow.toml）：
  1. 流式集合：[a, b] / {k: v}，可嵌套、可跨行（括号内换行不产生缩进 token，
     newline 由 parser skip_types 跳过）
  2. 锚点/别名：&anchor value（声明）/ *alias（引用）
  3. merge key：<<: *defaults（块映射与流式映射键位）
  4. 多文档：---（分隔）/ ...（流结束），顶层语句形态

yaml fixture / _parse / _node_names 见同目录 conftest.py。
"""

from tests.languages.yaml.conftest import _parse, _node_names


class TestFlowCollections:
    """流式集合 [a, b] / {k: v}。"""

    def test_flow_seq_parses(self, yaml):
        ast = _parse("key: [a, b, c]\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "FlowSeq"
        items = entry.value.items.items  # FlowItemList.items
        assert [i.node_name for i in items] == ["Identifier"] * 3

    def test_flow_map_parses(self, yaml):
        ast = _parse("key: {a: 1, b: 2}\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "FlowMap"
        pairs = entry.value.items.items  # FlowPairList.items
        assert [p.node_name for p in pairs] == ["FlowPair", "FlowPair"]
        assert pairs[0].key.node_name == "Identifier"
        assert pairs[0].value.node_name == "Number"

    def test_nested_flow(self, yaml):
        """嵌套流式：[[1, 2], {x: [3, 4]}]。"""
        ast = _parse("key: [[1, 2], {x: [3, 4]}]\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "FlowSeq"
        outer = entry.value.items.items
        assert outer[0].node_name == "FlowSeq"
        assert outer[1].node_name == "FlowMap"
        inner_map = outer[1].items.items[0]
        assert inner_map.value.node_name == "FlowSeq"

    def test_empty_collections(self, yaml):
        ast = _parse("a: []\nb: {}\n", yaml)
        assert ast.sub_node[0].value.node_name == "FlowSeq"
        assert ast.sub_node[1].value.node_name == "FlowMap"

    def test_flow_multiline(self, yaml):
        """跨行流式集合：括号内换行不产生缩进 token（lexer bracket_depth 抑制）。"""
        ast = _parse("items: [1,\n        2,\n        3]\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "FlowSeq"
        assert len(entry.value.items.items) == 3

    def test_flow_seq_renders(self, yaml):
        ast = _parse("key: [a, b]\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "key: [a, b]" in out

    def test_flow_map_renders(self, yaml):
        ast = _parse("key: {a: 1}\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "key: {a: 1}" in out

    def test_flow_multiline_renders_flat(self, yaml):
        """跨行流式集合渲染回单行（渲染不保留输入换行）。"""
        ast = _parse("items: [1,\n        2]\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "items: [1, 2]" in out


class TestAnchorsAliases:
    """锚点 &anchor / 别名 *alias / merge key <<。"""

    def test_anchor_decl(self, yaml):
        ast = _parse("x: &anchor value\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "AnchorValue"
        assert entry.value.name == "anchor"
        assert entry.value.value.node_name == "Identifier"

    def test_alias_ref(self, yaml):
        ast = _parse("y: *anchor\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "AliasRef"
        assert entry.value.name == "anchor"

    def test_anchor_on_collection(self, yaml):
        """锚点挂在集合上：&a [1, 2]。"""
        ast = _parse("x: &a [1, 2]\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "AnchorValue"
        assert entry.value.name == "a"
        assert entry.value.value.node_name == "FlowSeq"

    def test_merge_key_block(self, yaml):
        """块映射 merge key：<<: *defaults。"""
        src = "defaults: &def\n    a: 1\nitem:\n    <<: *def\n    b: 2\n"
        ast = _parse(src, yaml)
        defaults = ast.sub_node[0]
        assert defaults.value.node_name == "AnchorValue"
        item = ast.sub_node[1]
        assert item.value.node_name == "IndentBlock"
        merge_entry = item.value.sub_node[0]
        assert merge_entry.key.node_name == "MergeKey"
        assert merge_entry.value.node_name == "AliasRef"

    def test_merge_key_flow(self, yaml):
        """流式映射 merge key：{<<: *def, b: 2}。"""
        ast = _parse("m: {<<: *def, b: 2}\n", yaml)
        entry = ast.sub_node[0]
        pairs = entry.value.items.items
        assert pairs[0].key.node_name == "MergeKey"
        assert pairs[0].value.node_name == "AliasRef"

    def test_anchor_renders(self, yaml):
        ast = _parse("x: &a 1\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "x: &a 1" in out

    def test_merge_renders(self, yaml):
        ast = _parse("m: {<<: *def}\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "m: {<<: *def}" in out


class TestMultiDocument:
    """多文档分隔 --- / 流结束 ...。"""

    def test_multi_doc_parses(self, yaml):
        ast = _parse("---\ndoc1: v1\n---\ndoc2: v2\n...\n", yaml)
        names = _node_names(ast)
        assert names == [
            "DocStart",
            "MappingEntry",
            "DocStart",
            "MappingEntry",
            "DocEnd",
        ]

    def test_multi_doc_renders(self, yaml):
        src = "---\ndoc1: v1\n---\ndoc2: v2\n...\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "---" in out
        assert "doc1: v1" in out
        assert "doc2: v2" in out
        assert "..." in out

    def test_single_doc_no_marker(self, yaml):
        """无分隔符的单文档不受影响（回归：现有路径）。"""
        ast = _parse("key: value\n", yaml)
        assert _node_names(ast) == ["MappingEntry"]
