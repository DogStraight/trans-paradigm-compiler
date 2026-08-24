"""traversal.py — AnalysisTraversal

Primitive-driven semantic analysis pipeline.
Walks the AST and executes registered analyzer primitives according
to TOML [RuleName.analyzer] configuration for each node.
"""

from typing import Any
from core.define import Node
from core.config_registry import declare_cfg
from .scope import Scope, Symbol
from .context import AnalysisContext
from .diagnostic import Diagnostic
from .primitives import (
    get_primitive,
)

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# analyzer.root_scope
#   格式: dict — { name: str, kind: str }
#   根作用域名/种类（默认 "<global>" / "global"）；语言包可在 [analyzer] 段
#   显式声明（如 root_scope = { name = "<global>", kind = "global" }）。
_root_scope_cfg: dict = declare_cfg(
    "analyzer.root_scope",
    {"name": "<global>", "kind": "global"},
    __name__,
    "_root_scope_cfg",
)


class AnalysisTraversal:
    """原语驱动的语义分析管线

    遍历 AST，对每个节点根据 TOML [RuleName.analyzer] 配置
    依次执行注册的分析器原语。
    """

    def __init__(self, grammar_rules: dict[str, Any]):
        self._rules = grammar_rules
        self._primitive_order = self._load_primitive_order()
        self._root_scope: Scope | None = None
        self._current_scope: Scope | None = None
        self._all_symbols: list[Symbol] = []
        self._context = AnalysisContext()
        self._scope_name_node_ids: set[int] = set()
        # 外部注入的跨文件状态（ProjectChecker 在 analyze() 前写入，
        # analyze() 创建新 context 后合并进 extra）：原语/postpass 通过
        # context.extra 读取（如 module_index / inst_sites）。
        self._external_extra: dict[str, Any] = {}

    @staticmethod
    def _load_primitive_order() -> list[str]:
        try:
            from core.plugin_loader import get_primitive_order
            order = get_primitive_order()
            if order:
                return order
        except ImportError:
            pass
        return [
            "symbol_declare",
            "scope_enter",
            "identifier_resolve",
            "scope_exit",
        ]

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回带 _symbol_ref 的 AST"""
        self._root_scope = Scope(
            name=_root_scope_cfg.get("name", "<global>"),
            kind=_root_scope_cfg.get("kind", "global"),
        )
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._context = AnalysisContext(root_scope=self._root_scope)
        if self._external_extra:
            self._context.extra.update(self._external_extra)
        self._scope_name_node_ids.clear()
        self._pending_name_refs: list[tuple] = []
        self._walk(ast)
        self._resolve_pending()
        self._run_postpasses()
        return ast

    def _run_postpasses(self) -> None:
        """遍历后统一执行插件的 post-pass 钩子（ADR-0004）。

        节点锚定原语在遍历期收集，postpass 在遍历结束后走查跨节点/跨文件
        状态（赋值链、模块实例化联动等），向 context.report 报诊断。
        跨文件信息（模块索引等）由调用方（ProjectChecker）注入
        context.extra。
        """
        try:
            from core.plugin_loader import get_analyzer_postpasses
        except ImportError:
            return
        for fn in get_analyzer_postpasses():
            fn(self, self._context)

    def _resolve_pending(self) -> None:
        """遍历后统一核对暂存的名称引用。

        单遍遍历时声明可能在调用后方（前向引用，如 task 定义在模块尾、
        调用在 always 内），遍历结束时符号表已满——用同一 scope 对象重新
        resolve，仍无才报诊断（避免前向引用误报）。供各名称检查原语
        （identifier_resolve / check_name_call）失败时暂存。
        """
        for scope, name, node in self._pending_name_refs:
            if scope.resolve(name) is None:
                self._context.node = node
                self._context.report(
                    f"未解析的名称引用: '{name}'", code="W002", level="warning"
                )
        self._pending_name_refs = []

    @property
    def has_errors(self) -> bool:
        return len(self._context.diagnostics) > 0

    @property
    def root_scope(self) -> Scope | None:
        return self._root_scope

    @property
    def all_symbols(self) -> list[Symbol]:
        return self._all_symbols

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return self._context.diagnostics

    # ── 递归遍历核心 ──

    def _walk(self, node: Any) -> None:
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        rule = self._rules.get(node.node_name)
        config = getattr(rule, "analyzer", {}) if rule else {}
        self._context.node = node
        self._context.config = config

        # 标准原语
        po = self._primitive_order
        for prim_name in po:
            if prim_name == "scope_exit":
                continue
            prim = get_primitive(prim_name)
            if prim is None:
                continue
            if _is_primitive_triggered(prim_name, config):
                prim(self, node, config)

        # 自定义原语：primitives 列表 + 配置键同名触发（如 check_name_call = {...}
        # ——键名即原语名，一个键同时触发并携带配置，避免 primitives 列表 + 单独
        # 配置段两处配合的费解写法）。两者合并去重；跳过标准原语与元键 primitives。
        po_set = set(po)
        custom_names: list[str] = []
        seen: set[str] = set()
        for prim_name in config.get("primitives", []):
            if prim_name not in seen and prim_name not in po_set:
                custom_names.append(prim_name)
                seen.add(prim_name)
        for prim_name in config:
            if prim_name in seen or prim_name in po_set or prim_name == "primitives":
                continue
            if get_primitive(prim_name) is not None:
                custom_names.append(prim_name)
                seen.add(prim_name)
        for prim_name in custom_names:
            prim = get_primitive(prim_name)
            if prim is not None:
                prim(self, node, config)

        # 递归子节点
        for child in node.iter_children():
            self._walk(child)

        # scope_exit
        scope_exit_prim = get_primitive("scope_exit")
        if scope_exit_prim is not None:
            if _is_primitive_triggered("scope_exit", config):
                scope_exit_prim(self, node, config)


# ── 辅助函数 ──


def _is_primitive_triggered(prim_name: str, config: dict) -> bool:
    """判断指定原语是否应被当前配置触发

    原语与 TOML 配置字段的映射关系：
        symbol_declare     → config.symbol 存在
        scope_enter        → config.scope 存在
        scope_exit         → config.scope 存在
        identifier_resolve → config.identifier_ref 为真
    """
    if not config:
        return False

    if prim_name in ("symbol_declare",):
        if "symbol" in config:
            return True
        # 无显式 symbol：scope 带 name_attr 即推断声明符号（见 _symbol.symbol_declare）
        scope_meta = config.get("scope")
        return bool(
            isinstance(scope_meta, dict) and scope_meta.get("name_attr")
        )
    if prim_name in ("scope_enter", "scope_exit"):
        return "scope" in config
    if prim_name == "identifier_resolve":
        return bool(config.get("identifier_ref", False))

    # 未知原语：由 TOML 中的 primitives 列表控制（未来扩展）
    primitives_list = config.get("primitives", [])
    if isinstance(primitives_list, list):
        return prim_name in primitives_list
    return False
