"""tests/languages/yaml/test_yaml_plain.py — 裸标量（plain scalar）扫描。

对应 grammar/yaml/base/_token.toml 的 [plain] 段（lexer plain 分支）：
  1. 字符集：真实配置值的常见形态——CI 表达式 ${{ }}、URL/路径（/ @）、
     镜像 tag（词内冒号）、中缀连字符（windows-latest）、多词值（echo hi）、
     词内 #（abc#def，非注释）
  2. 终止规则：':' 后随空白/行尾 = 映射分隔（stop_space_after）；锚点/别名
     名是单词（no_space_after_tokens）；括号内 { } 终止（flow_terminators，
     流式集合不破）；' #' 前终止（# 留给注释分支）
  3. 关键字精化：true/false/null 仍为 keyword（BoolLit/NullLit 不变）
  4. 既有形态零回归：流式集合/锚点/块标量/文档标记

yaml fixture / _parse / _node_names 见同目录 conftest.py。
"""

from tests.languages.yaml.conftest import _parse, _node_names


class TestPlainValueForms:
    """真实配置值的常见形态。"""

    def test_ci_expression(self, yaml):
        """${{ matrix.os }}——CI 表达式（{ } 块语境吸收）。"""
        ast = _parse("runs-on: ${{ matrix.os }}\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "Identifier"
        assert entry.value.content == "${{ matrix.os }}"

    def test_url_at(self, yaml):
        ast = _parse("uses: actions/checkout@v5\n", yaml)
        assert ast.sub_node[0].value.content == "actions/checkout@v5"

    def test_image_tag_colon(self, yaml):
        """词内冒号（: 后随非空白）。"""
        ast = _parse("image: nginx:1.25\n", yaml)
        assert ast.sub_node[0].value.content == "nginx:1.25"

    def test_dash_word(self, yaml):
        ast = _parse("os: windows-latest\n", yaml)
        assert ast.sub_node[0].value.content == "windows-latest"

    def test_multiword(self, yaml):
        """多词值（词内空格是内容）。"""
        ast = _parse("run: echo hello world\n", yaml)
        assert ast.sub_node[0].value.content == "echo hello world"

    def test_path_with_colons(self, yaml):
        """./data:/usr/share/nginx/html——词内冒号 + 点开头。"""
        ast = _parse("volume: ./data:/usr/share/nginx/html\n", yaml)
        assert ast.sub_node[0].value.content == "./data:/usr/share/nginx/html"

    def test_hash_inside_word(self, yaml):
        """abc#def——# 前无空格是词的一部分（不截断为注释）。"""
        ast = _parse("hash: abc#def\n", yaml)
        assert ast.sub_node[0].value.content == "abc#def"

    def test_trailing_comment(self, yaml):
        """' #' 前终止，注释独立。"""
        ast = _parse("port: 8080 # note\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "Number"


class TestPlainTermination:
    def test_flow_seq_still_works(self, yaml):
        """[a, b] 流式序列：] 不吞进 plain（flow 终止）。"""
        ast = _parse("key: [a, b]\n", yaml)
        entry = ast.sub_node[0]
        assert entry.value.node_name == "FlowSeq"
        items = entry.value.items.items
        assert [i.content for i in items] == ["a", "b"]

    def test_flow_map_plain_value_adjacent_brace(self, yaml):
        """{k: v} 流式映射：} 不吞进 plain 值（括号内 flow 终止）。"""
        ast = _parse("m: {a: 1, b: x}\n", yaml)
        pairs = ast.sub_node[0].value.items.items
        assert pairs[1].value.content == "x"

    def test_nested_flow_maps(self, yaml):
        ast = _parse("k: {x: {y: z}}\n", yaml)
        inner = ast.sub_node[0].value.items.items[0]
        assert inner.value.node_name == "FlowMap"

    def test_anchor_name_is_word(self, yaml):
        """&anchor value——锚点名遇空格终止，value 独立。"""
        ast = _parse("x: &anchor value\n", yaml)
        av = ast.sub_node[0].value
        assert av.node_name == "AnchorValue"
        assert av.name == "anchor"
        assert av.value.content == "value"

    def test_alias_name(self, yaml):
        ast = _parse("y: *anchor\n", yaml)
        assert ast.sub_node[0].value.name == "anchor"

    def test_merge_key_flow(self, yaml):
        """{<<: *def} 流式 merge key 完整往返。"""
        ast = _parse("m: {<<: *def}\n", yaml)
        pair = ast.sub_node[0].value.items.items[0]
        assert pair.key.node_name == "MergeKey"
        assert pair.value.node_name == "AliasRef"

    def test_keyword_refinement(self, yaml):
        """true/null 仍是关键字（BoolLit/NullLit 不受 plain 影响）。"""
        ast = _parse("b: true\nn: null\nf: false\n", yaml)
        values = [e.value.node_name for e in ast.sub_node]
        assert values == ["BoolLit", "NullLit", "BoolLit"]

    def test_doc_markers_intact(self, yaml):
        """--- 与 ... 仍为文档标记（extend 符号优先于 plain 的 . 触发）。"""
        ast = _parse("---\ndoc1: v1\n...\n", yaml)
        assert _node_names(ast) == ["DocStart", "MappingEntry", "DocEnd"]

    def test_block_scalar_intact(self, yaml):
        """块标量触发不受 plain 影响。"""
        ast = _parse("run: |\n  cmd\n", yaml)
        assert ast.sub_node[0].value.node_name == "BlockScalar"

    def test_value_stops_at_newline(self, yaml):
        """plain 值不跨行（下一行是新的条目）。"""
        ast = _parse("a: v1\nb: v2\n", yaml)
        assert ast.sub_node[0].value.content == "v1"
        assert ast.sub_node[1].value.content == "v2"


class TestPlainRender:
    def test_comment_nodes_render(self, yaml):
        """独立注释渲染保真（[Comment] 规则使注释节点有布局，不静默丢弃）。"""
        ast = _parse("# hello\nkey: v\n", yaml)
        out = yaml["renderer"].render(ast)
        assert "# hello" in out

    def test_roundtrip_ci_style(self, yaml):
        """CI 风格完整往返。"""
        src = (
            "jobs:\n"
            "  build:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    steps:\n"
            "      - uses: actions/checkout@v5\n"
            "      - name: Test\n"
            "        run: |\n"
            "          python -m pytest\n"
        )
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "runs-on: ${{ matrix.os }}" in out
        assert "uses: actions/checkout@v5" in out
        assert _node_names(_parse(out, yaml)) == _node_names(ast)

    def test_plain_content_roundtrip(self, yaml):
        src = "a: ./x:/y\nb: echo hi\nc: abc#def\n"
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "./x:/y" in out
        assert "echo hi" in out
        assert "abc#def" in out


class TestRealWorkflowFiles:
    """真实 GitHub Actions workflow 文件（项目自身 .github/workflows/）。"""

    _FILES = [
        (".github/workflows/ci.yml", "ci"),
        (".github/workflows/nightly.yml", "nightly"),
    ]

    def test_real_workflow_files_parse_and_roundtrip(self, yaml):
        """真实 workflow：tokenize 不崩、parse 不 truncated、渲染往返一致。"""
        import os

        root = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."
        )
        for rel, _name in self._FILES:
            path = os.path.join(root, rel)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            tokens = yaml["lexer"].tokenize(src)  # 不抛 = 字符集覆盖充分
            ast = yaml["parser"].parse(tokens)
            assert not getattr(ast, "_parse_truncated", False), rel
            unit = getattr(yaml["lexer"], "_indent_unit", None)
            if isinstance(unit, int) and unit > 0:
                ast.add_attr("_indent_unit", unit)
            out = yaml["renderer"].render(ast)
            ast2 = _parse(out, yaml)
            n1 = _node_names(ast)
            n2 = _node_names(ast2)
            assert n1 == n2, f"{rel}: 往返结构不一致 {n1} vs {n2}"

    def test_real_workflow_keeps_key_values(self, yaml):
        """关键形态抽查：块标量 run、CI 表达式、路径值都在渲染输出中。"""
        import os

        root = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."
        )
        with open(os.path.join(root, ".github/workflows/ci.yml"), encoding="utf-8") as f:
            src = f.read()
        ast = _parse(src, yaml)
        out = yaml["renderer"].render(ast)
        assert "${{ matrix.os }}" in out
        assert "run: |" in out
        assert "actions/checkout" in out
        assert "# CI" in out or "name: CI" in out  # 头部注释/首键保真
