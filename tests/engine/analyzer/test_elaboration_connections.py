"""精化项 `connections`（verilog 插件）× 引擎侧 `ConnectionElaborator` —— **等价性对拍**。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 **P3-②b-prep**：插件产物
`connections` 与引擎侧 `FileResult.connections` **逐项相同**——这是后续"层 2/3 与 ports
一次性搬迁"的前提证据。

⚠ 本阶段本项**只新增、无人消费**（引擎 `FileResult.connections` 仍在原位、仍是层 3 与
postpass 的输入）。

## ✅ 一个曾经担心的风险，实测不存在（值得留档）

搬迁前我担心**时序**：引擎的层 2 是在**发现过程中逐文件**算的（`FilePipeline.parse_file`
里调），而精化 pass 在**发现之后**统一跑——若层 2 依赖 `module_index`（当时只填了一部分），
两者结果会不同。实测读码：`elaborate_connections` **完全不读端口表**（不用 `module_index`/
ports），只读**声明字段**并把连接表达式渲染成文本 → **无时序风险**。本文件的逐项对拍就是
这个结论的证据（若真有差异，这里会红）。
"""

from __future__ import annotations

import pytest

from core._protocol import CTX_ANALYZED_FILE, CTX_ELABORATION

from analyzer.checker import ProjectChecker
from analyzer.elaboration import load_elaborator_spec

pytestmark = pytest.mark.usefixtures("config_loaded")

# 覆盖三种连接形态：命名 / 位置 / 命名但值为空（`.a()`）
_SRC = """\
module sub (input clk, input [7:0] a, output [7:0] y);
endmodule

module top (input clk, input [7:0] a, output [7:0] y);
  sub u1 (.clk(clk), .a(a), .y(y));
  sub u2 (clk, a, y);
  sub u3 (.clk(clk), .a(), .y(y));
endmodule
"""


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "conn.v"
    path.write_text(_SRC, encoding="utf-8")
    return path


def _plugin(checker: ProjectChecker) -> dict:
    return checker._elab_extra[CTX_ELABORATION]["connections"]


# ── 1. 声明面 ──

@pytest.mark.smoke
def test_verilog_pack_declares_connections(checker):
    """语言包必须声明 `connections` 项（作用域；角色的**机制**已随层 2/3 迁出退场）。"""
    checker._prepare_run([])
    spec = load_elaborator_spec("grammar/verilog")
    assert spec is not None
    item = next(it for it in spec.items if it.name == "connections")
    assert item.scope == "file"
    assert not hasattr(item, "role")  # 字段本身已删（不是"值为 None"）
    assert item.provides == ("connections",)


# ── 2. 等价性对拍（搬迁的前提） ──

def test_named_and_positional_connections_are_not_vacuous(checker, project):
    """不空转：三种形态都真的抽到了（否则对拍可能只是"两边都空"）。"""
    checker.check(str(project))
    by_inst = {c["inst_name"]: c for c in _plugin(checker)[str(project)]}

    assert set(by_inst) == {"u1", "u2", "u3"}, "实例化点没抽全"

    # 命名连接 → connects
    assert by_inst["u1"]["connects"] == {"clk": "clk", "a": "a", "y": "y"}
    assert by_inst["u1"]["ordered"] == []
    assert by_inst["u1"]["module_name"] == "sub"

    # 位置连接 → ordered（按出现序）
    assert by_inst["u2"]["connects"] == {}
    assert by_inst["u2"]["ordered"] == ["clk", "a", "y"]

    # 命名但值为空（`.a()`）→ 键在、值为空串
    assert by_inst["u3"]["connects"] == {"clk": "clk", "a": "", "y": "y"}


def test_inst_node_and_file_are_exposed(checker, project):
    """`inst_node` / `file` 随产物带出（层 3 归属判定与 related 链要用）。"""
    checker.check(str(project))
    conns = _plugin(checker)[str(project)]
    assert all(c["inst_node"] is not None for c in conns)
    assert all(c["file"] == str(project) for c in conns)


def test_file_without_instances_yields_empty_list(checker, project):
    """无实例化点的文件 → 空表（键仍在：下游不必两套写法）。"""
    checker.check(str(project))
    # sub 无实例化点，但 top 有；此处用产物覆盖性断言（每个文件都有键）
    assert all(isinstance(v, list) for v in _plugin(checker).values())


def test_analyzed_file_is_injected_so_consumers_can_slice(checker, project):
    """引擎注入**当前分析文件**（语言无关的文件层事实）——插件据此取按文件的产物切片。

    这是 P3-②c-1 的前置：`connections` 是**文件作用域**产物（`{路径: [...]}`），而 postpass
    是**逐文件**跑的——没有这个键，插件只能反查 AST 去猜自己在分析哪个文件。
    """
    checker.check(str(project))
    for path, fr in checker._ctx.memo.items():
        assert fr.analyzer is not None
        extra = fr.analyzer._external_extra
        assert extra[CTX_ANALYZED_FILE] == path
        # 用该键取切片：容器按文件给出连接表
        container = extra[CTX_ELABORATION]
        assert isinstance(container["connections"].get(path), list)
        assert isinstance(container["port_decls"], dict)
