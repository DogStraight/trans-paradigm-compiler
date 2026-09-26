"""精化**服务句柄**（`analyzer/elaboration/service.py`）—— 引擎给插件的语言无关访问面。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 决策 1 的③「语言无关服务句柄」：
插件求解器不从引擎内部偷状态——通用能力（渲染 / 列出已发现文件 / 按单元名取节点与定义
文件）**只经这个面**取，且这些面**全部语言无关**（"有哪些文件""名字叫什么单元""节点在哪"
与语言无关；语言语义仍只在插件里）。

⚠ 本文件是 **P3-②b 层 3 移植的前置**：层 3 的驱动穿透要按单元名取单元子树与它所在的
文件（否则只能靠引擎内部对象），故先把这个面立起来并锁住。
"""

from __future__ import annotations

import pytest

from core.define import Node

from analyzer.checker import ProjectChecker
from analyzer.elaboration.service import ElaborationService

pytestmark = pytest.mark.usefixtures("config_loaded")

_SRC = "module top (input clk);\nendmodule\n"


# ── 1. 面本身（替身会话，逐项断言） ──

class _Fr:
    def __init__(self, path: str, ast=None) -> None:
        self.path = path
        self.ast = ast


class _Info:
    def __init__(self, node=None, file: str = "") -> None:
        self.node = node
        self.file = file


class _Session:
    """替身会话：只提供本服务需要的三样（结构上满足 `StructureCtx`）。"""

    def __init__(self, memo: dict, index: dict) -> None:
        self.memo = memo
        self.module_index = index
        self.rendered: list = []

    def render_subtree(self, node) -> str:
        self.rendered.append(node)
        return f"<{node.node_name}>"


def test_render_delegates_without_reimplementing():
    unit = Node("ModuleDecl")
    session = _Session({"a.v": _Fr("a.v", Node("Root"))}, {})
    svc = ElaborationService(session)
    assert svc.render(unit) == "<ModuleDecl>"
    assert session.rendered == [unit], "render 应**转交**引擎助手，不自己实现"


def test_files_and_unit_lookups():
    unit = Node("ModuleDecl")
    ast = Node("Root")
    session = _Session(
        {"a.v": _Fr("a.v", ast), "b.v": _Fr("b.v", None)},
        {"top": _Info(unit, "a.v")},
    )
    svc = ElaborationService(session)

    assert svc.files() == [("a.v", ast), ("b.v", None)], "顺序 = 发现序（层 3 依赖确定性）"
    assert svc.unit_node("top") is unit
    assert svc.unit_file("top") == "a.v"
    # 未定义单元 → None / ""（不抛）
    assert svc.unit_node("missing") is None
    assert svc.unit_file("missing") == ""


# ── 2. 真实会话（面必须反映引擎侧实际状态） ──

@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def test_service_reflects_real_session(checker, tmp_path):
    src = tmp_path / "unit.v"
    src.write_text(_SRC, encoding="utf-8")
    checker.check(str(src))

    svc = ElaborationService(checker._ctx)
    # 文件面 = 引擎 memo（同序）
    assert [p for p, _ in svc.files()] == list(checker._ctx.memo)
    assert all(
        svc_ast is fr.ast for (_, svc_ast), fr in zip(svc.files(), checker._ctx.memo.values())
    )
    # 单元面 = 引擎单元索引
    engine_info = checker._ctx.module_index["top"]
    assert svc.unit_node("top") is engine_info.node
    assert svc.unit_file("top") == engine_info.file
    top_node = svc.unit_node("top")
    assert top_node is not None
    assert top_node.node_name == "ModuleDecl"
