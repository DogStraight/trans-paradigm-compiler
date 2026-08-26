"""transform 注释迁移测试（注释节点模型步骤 3，P1.5）。

migrate_comments：新节点继承被替换节点的注释（_comment_slots 槽位 +
_attached_comments 行尾 attachment）——变换路径注释随结构走
（impl → ModuleInst 后注释出现在生成的实例节点上）。
"""

from core.define import Node
from transform.engine import migrate_comments


def _stmt(text: str, slots=None, attached=None) -> Node:
    n = Node("Stmt", value=text)
    if slots:
        n.add_attr("_comment_slots", slots)
    if attached:
        n.add_attr("_attached_comments", attached)
    return n


class TestMigrateComments:
    def test_slots_migrated(self):
        old = _stmt("impl", slots={"trailing": ["// 实例化注释"]})
        new = Node("ModuleInst", module_name="spi_master")
        out = migrate_comments(old, new)
        assert out is new
        assert new._comment_slots == {"trailing": ["// 实例化注释"]}

    def test_attached_migrated(self):
        old = _stmt("impl", attached=["// 行尾"])
        new = Node("ModuleInst")
        migrate_comments(old, new)
        assert new._attached_comments == ["// 行尾"]

    def test_slots_merged_into_existing(self):
        old = _stmt("impl", slots={"trailing": ["// 旧注释"]})
        new = Node("ModuleInst")
        new.add_attr("_comment_slots", {"leading": ["// 新注释"]})
        migrate_comments(old, new)
        assert new._comment_slots == {
            "leading": ["// 新注释"],
            "trailing": ["// 旧注释"],
        }

    def test_no_slots_noop(self):
        old = _stmt("impl")
        new = Node("ModuleInst")
        out = migrate_comments(old, new)
        assert out is new
        assert not hasattr(new, "_comment_slots")
        assert not hasattr(new, "_attached_comments")

    def test_same_node_noop(self):
        n = _stmt("x", slots={"trailing": ["// c"]})
        out = migrate_comments(n, n)
        assert out is n
        assert n._comment_slots == {"trailing": ["// c"]}

    def test_non_node_skipped(self):
        out = migrate_comments("str", Node("ModuleInst"))
        assert out is not None and out.node_name == "ModuleInst"
        assert not hasattr(out, "_comment_slots")


class TestImplCommentMigrationE2E:
    """管线路径：impl 行尾注释变换后出现在生成的实例节点（变换路径注释
    随结构走——此前变换路径普通注释必丢）。"""

    SRC = """module top(
    input clk
);
    impl spi.master (.clk(clk)) => top; // spi master 实例化注释
endmodule

type spi {
    master : input clk, input miso, output mosi, output cs;
    impl [master] (
        input clk,
        output sck
    ) {
    }
}
"""

    def test_comment_appears_in_generated_inst(self):
        from pipeline import run_pipeline_on_source

        r = run_pipeline_on_source(
            source=self.SRC, rules_dir="grammar/verilog", quiet=True,
            no_lint=True, format_output=False,
        )
        assert r["success"], r.get("error", "")
        out = r.get("output", "")
        assert "spi_master" in out, "impl 应变换为 ModuleInst"
        assert "spi master 实例化注释" in out, "impl 注释应迁移到实例"

    def test_comment_migrated_after_transform(self):
        """变换后 AST 的 ModuleInst 携带注释（结构级，非文本级）。"""
        from pipeline import run_pipeline_on_source

        r = run_pipeline_on_source(
            source=self.SRC, rules_dir="grammar/verilog", quiet=True,
            no_lint=True, format_output=False,
        )
        ast = r.get("ast")
        found = []

        def deep(obj):
            if isinstance(obj, Node):
                if obj.node_name == "ModuleInst":
                    found.append(
                        (getattr(obj, "_comment_slots", None),
                         getattr(obj, "_attached_comments", None))
                    )
                for k, v in list(vars(obj).items()):
                    if k.startswith("_"):
                        continue
                    deep(v)
            elif isinstance(obj, dict):
                for v in obj.values():
                    deep(v)
            elif isinstance(obj, list):
                for v in obj:
                    deep(v)

        deep(ast)
        assert found, "变换后应有 ModuleInst"
        slots, attached = found[0]
        assert (slots or {}).get("trailing") == ["// spi master 实例化注释"] or (
            attached == ["// spi master 实例化注释"]
        ), f"注释未迁移到实例: {found[0]}"

    def test_subtree_comment_migrated(self):
        """注释挂在被替换节点子树（如 instance_name 的 Identifier）时也迁移
        （deep 收集）——`spi.slave spi_io // 注释` 展开为多端口后注释在
        第一个产物。"""
        from pipeline import run_pipeline_on_source

        src = """module top(
    input clk,
    spi.slave spi_io // slave 接口注释
);
endmodule

type spi {
    slave  : input clk, input mosi, output miso, output cs;
}
"""
        r = run_pipeline_on_source(
            source=src, rules_dir="grammar/verilog", quiet=True,
            no_lint=True, format_output=False,
        )
        assert r["success"], r.get("error", "")
        out = r.get("output", "")
        assert "spi_io_clk" in out, "端口应展开"
        assert "// slave 接口注释" in out, "子树注释应迁移到第一个产物"
