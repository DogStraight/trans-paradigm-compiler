"""token span 绑定（P3.1，0.1.2 阶段 0）——解析成功节点挂 `_tok_span`。

阶段目标：AST 规则节点带 token 范围（半开 `[start, end)`，token 流索引），
供增量重解析（P3.2）结构对齐定位。断言：

- span 存在且区间合法（0 <= start < end）
- 父节点 span 包含子节点 span
- `dump()` 不含 `_tok_span`（下划线元数据不进序列化，防污染 AST 快照）
- 回溯场景下 span 仍合法且确定（失败尝试不残留错误范围）

实现：parser/_production.py try_plain_rule / try_block_rule 成功返回前写入；
声明 core/define.py `Node._tok_span`。
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

_SRC = """module m (
    input  wire clk,
    output wire q
);
    wire a;
    assign a = clk;
    always @(posedge clk) begin
        q <= a;
    end
endmodule
"""

# 回溯场景：层次引用与目标位消歧（batch9 形态——候选规则先失败再成功）
_BACKTRACK_SRC = """module bt;
    wire [3:0] a;
    wire b;
    assign a[0].x = b;
endmodule
"""


def _parse(src: str):
    res = run_pipeline_on_source(source=src, quiet=True, no_lint=True, stage="parse")
    assert res["success"], res.get("error")
    return res["ast"]


def _walk(node):
    yield node
    for child in node.iter_children():
        yield from _walk(child)


def test_tok_span_present_and_valid():
    """规则节点带 span，区间合法（半开，start < end）。"""
    ast = _parse(_SRC)
    with_span = [n for n in _walk(ast) if getattr(n, "_tok_span", None)]
    assert with_span, "解析成功但没有任何节点带 _tok_span"
    for n in with_span:
        start, end = n._tok_span
        assert 0 <= start < end, (n.node_name, n._tok_span)


def test_tok_span_nested_containment():
    """父节点 span 包含子节点 span（结构对齐前提）。"""
    ast = _parse(_SRC)
    checked = 0
    for parent in _walk(ast):
        pspan = getattr(parent, "_tok_span", None)
        if not pspan:
            continue
        for child in parent.iter_children():
            cspan = getattr(child, "_tok_span", None)
            if not cspan:
                continue
            assert pspan[0] <= cspan[0] and cspan[1] <= pspan[1], (
                parent.node_name, pspan, child.node_name, cspan
            )
            checked += 1
    assert checked > 0, "没有可校验的父子 span 对"


def test_tok_span_excluded_from_dump():
    """`_tok_span` 是引擎元数据（下划线前缀）——不进 dump/序列化。"""
    ast = _parse(_SRC)
    assert "_tok_span" not in repr(ast.dump())


def test_tok_span_valid_after_backtrack():
    """回溯场景（消歧候选失败再成功）下 span 合法，且失败尝试不残留错误范围。"""
    ast = _parse(_BACKTRACK_SRC)
    spans = [n._tok_span for n in _walk(ast) if getattr(n, "_tok_span", None)]
    assert spans, "回溯输入解析后无 span"
    for start, end in spans:
        assert 0 <= start < end
    # 确定性：同输入两次解析 span 集合一致（回溯不引入非确定残留）
    ast2 = _parse(_BACKTRACK_SRC)
    spans2 = [n._tok_span for n in _walk(ast2) if getattr(n, "_tok_span", None)]
    assert spans == spans2
