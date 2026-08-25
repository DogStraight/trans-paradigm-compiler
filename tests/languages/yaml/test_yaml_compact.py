"""tests/languages/yaml/test_yaml_compact.py — 行内映射（compact mapping）+ 缩进单位推导。

覆盖两件事（对应 grammar/yaml/00_document.toml 的 CompactMap/SeqValue 规则
与 base/_lexer.toml 的 [indent] level="auto"）：
  1. CompactMap：`- name: Test` + 同列对齐续块（`  run: |` 兄弟成员）——
     CI 配置文件的核心形态
  2. 歧义分流：`- name:`（无行内值 → 嵌套值）/ `- name: Test`（行内值 →
     兄弟续块）/ `- a`（普通标量回退）
  3. auto 缩进单位：首次结构缩进行锁定（2/4/6 空格文件均可用），注释行
     不参与锁定；渲染与源单位一致（_indent_unit 盖章，见 conftest）

yaml fixture / _parse / _node_names 见同目录 conftest.py。
"""

from tests.languages.yaml.conftest import _parse, _node_names


class TestCompactMapParse:
    def test_compact_with_continuation_block(self, yaml):
        """`- name: Test` + 对齐续块 → CompactMap.rest 吃入（2 空格源）。"""
        ast = _parse(
            "steps:\n  - name: Test\n    run: |\n      cmd1\n    with: key\n",
            yaml,
        )
        steps = ast.sub_node[0]
        item = steps.value.sub_node[0]
        assert item.value.node_name == "CompactMap"
        cmap = item.value
        assert cmap.first.key.content == "name"
        assert cmap.first.value.content == "Test"
        # rest = 兄弟续块（run + with 两对）
        rest = cmap.rest
        assert rest.node_name == "IndentBlock"
        assert [e.key.content for e in rest.sub_node] == ["run", "with"]

    def test_compact_single_pair_no_rest(self, yaml):
        """`- name: Test` 无续块 → CompactMap.rest 为空。"""
        ast = _parse("- name: Test\n- other\n", yaml)
        item = ast.sub_node[0]
        assert item.value.node_name == "CompactMap"
        assert not hasattr(item.value, "rest")

    def test_no_inline_value_nests(self, yaml):
        """`- name:` 无行内值 → 深缩进块是嵌套值（不是兄弟）。"""
        ast = _parse("- name:\n    sub: 1\n", yaml)
        item = ast.sub_node[0]
        assert item.value.node_name == "CompactMap"
        cmap = item.value
        # 值块被 MappingEntry 的 @Value? 吃入（嵌套值语义，非 rest）
        assert cmap.first.value.node_name == "IndentBlock"
        assert not hasattr(cmap, "rest")

    def test_plain_scalar_falls_back(self, yaml):
        """`- a` 普通标量回退 @Value（不误判为映射）。"""
        ast = _parse("- a\n- 42\n- true\n", yaml)
        values = [i.value.node_name for i in ast.sub_node]
        assert values == ["Identifier", "Number", "BoolLit"]

    def test_flow_values_fall_back(self, yaml):
        """`- [a, b]` 流式序列值回退。"""
        ast = _parse("- [a, b]\n", yaml)
        assert ast.sub_node[0].value.node_name == "FlowSeq"

    def test_nested_compact_inside_block(self, yaml):
        """indent block 内嵌套 compact map（steps 形态）。"""
        ast = _parse(
            "steps:\n  - name: A\n    run: x\n  - name: B\n",
            yaml,
        )
        steps = ast.sub_node[0]
        assert steps.value.node_name == "IndentBlock"
        items = steps.value.sub_node
        assert [i.node_name for i in items] == ["SequenceItem", "SequenceItem"]
        assert items[0].value.node_name == "CompactMap"


class TestCompactMapRender:
    def test_compact_roundtrip_2space(self, yaml):
        """2 空格源渲染 → 与源同单位 → 往返一致。"""
        src = "steps:\n  - name: Test\n    run: |\n      cmd1\n      cmd2\n    with: key\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        # 结构断言：续对与 name 对齐（2 空格单位）
        assert "  - name: Test" in out
        assert "    run: |" in out
        assert "      cmd1" in out
        assert "    with: key" in out
        # 往返
        ast2 = _parse(out, yaml)
        assert _node_names(ast2) == _node_names(ast)

    def test_mixed_list_roundtrip(self, yaml):
        src = "- name: A\n- plain\n- name: B\n  key: 1\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert _node_names(_parse(out, yaml)) == _node_names(ast)


class TestAutoIndentUnit:
    def test_two_space_file(self, yaml):
        """2 空格缩进文件（真实 CI 约定）。"""
        ast = _parse("key:\n  sub: 1\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "IndentBlock"

    def test_six_space_file(self, yaml):
        ast = _parse("a:\n      b: 1\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "IndentBlock"

    def test_unit_locked_once_per_file(self, yaml):
        """同一 lexer 连续 tokenize 两个不同单位文件不串扰。"""
        a1 = _parse("k:\n  x: 1\n", yaml)
        a2 = _parse("k:\n    x: 1\n", yaml)
        assert a1.sub_node[0].value.node_name == "IndentBlock"
        assert a2.sub_node[0].value.node_name == "IndentBlock"

    def test_comment_lines_do_not_lock_unit(self, yaml):
        """注释行的奇怪缩进不锁定单位（3 空格注释 + 2 空格结构）。"""
        ast = _parse("# c\n   # odd indent\nkey:\n  sub: 1\n", yaml)
        # 顶层注释挂为 Comment 节点，过滤后取映射
        entries = [n for n in ast.sub_node if n.node_name == "MappingEntry"]
        entry = entries[0]
        assert entry.key.content == "key"
        assert entry.value.node_name == "IndentBlock"

    def test_render_matches_source_unit(self, yaml):
        """渲染输出用源文件锁定单位（非包默认 4）。"""
        ast = _parse("key:\n  sub: 1\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "  sub: 1" in out
        assert "    sub: 1" not in out


class TestCompactNested:
    def test_deep_nesting_mixed_units_roundtrip(self, yaml):
        """多层嵌套（compact + block + block scalar）完整往返。"""
        src = (
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Test\n"
            "        run: |\n"
            "          line1\n"
            "      - name: Lint\n"
            "        run: |\n"
            "          line2\n"
        )
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        ast2 = _parse(out, yaml)
        assert _node_names(ast2) == _node_names(ast)
        # 关键行渲染形态
        assert "      - name: Test" in out
        assert "        run: |" in out
        assert "          line1" in out
