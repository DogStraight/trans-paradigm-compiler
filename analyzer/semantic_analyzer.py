"""SemanticAnalyzer — scope management and symbol registration.

Walks the AST, manages scope enter/exit via rule self-declaration
(scope={}/symbol={} in TOML), registers explicitly declared symbols,
and resolves identifier references via scope chain lookup.

Advanced services (implicit decl, width eval, constant folding) are
provided by optional transform/post plugins.
"""

from typing import Dict, List, Optional, Any, Callable
from core.define import Node
from .scope import Scope, Symbol


# ── Capture 后处理器注册中心 ──
# 语言特定的 capture 后处理通过此系统注册，不硬编码在 analyzer 中。
# 注册: register_capture_hook("resolve_revert")(fn)
# 调用: 由 TOML 中 [RuleName.analyzer] capture_hooks = ["resolve_revert"] 触发

_capture_hooks: dict[str, Callable] = {}


def register_capture_hook(name: str) -> Callable:
    """装饰器：注册一个 capture 后处理器

    Hook 签名:
        def hook(node, sym_rule, scope, name, attrs) -> dict:
            # 修改 attrs 并返回
            return attrs
    """
    def decorator(fn: Callable) -> Callable:
        _capture_hooks[name] = fn
        return fn
    return decorator


class SemanticAnalyzer:
    """语义分析器：遍历 AST，注册声明，解析标识符引用"""

    def __init__(self, grammar_rules: Dict[str, Any], mapping_config: Optional[dict] = None):
        self._rules = grammar_rules
        self._root_scope: Optional[Scope] = None
        self._current_scope: Optional[Scope] = None
        self._all_symbols: List[Symbol] = []
        self._errors: List[str] = []
        self._unresolved_refs: List[str] = []
        # 语义映射配置（从 _analyzer.toml 加载）
        self._mapping_config: list[dict] = []
        if mapping_config:
            self._mapping_config = [
                v for v in mapping_config.values()
                if isinstance(v, dict) and "trigger" in v
            ]
        # 语义映射表
        self._semantic_mapping: dict = {}

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回带 _symbol_ref 的 AST（只读）"""
        self._root_scope = Scope(name="<global>", kind="global")
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._errors.clear()
        self._scope_name_node_ids: set[int] = set()
        self._unresolved_refs.clear()
        self._walk(ast)
        return ast

    @property
    def has_errors(self) -> bool:
        return len(self._errors) > 0 or len(self._unresolved_refs) > 0

    @property
    def root_scope(self) -> Optional[Scope]:
        return self._root_scope

    @property
    def all_symbols(self) -> List[Symbol]:
        return self._all_symbols

    @property
    def errors(self) -> List[str]:
        return self._errors

    @property
    def semantic_mapping(self) -> dict:
        return self._semantic_mapping

    # ---- 递归遍历核心 ----

    def _walk(self, node: Any) -> None:
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        rule = self._rules.get(node.node_name)
        scope = self._current_scope
        assert scope is not None, "analyze() must be called before walking"

        # 1. 声明符号（规则自声明，从 analyzer 配置读取）
        #    在进入新作用域之前执行，确保符号注册到父作用域而非自身作用域。
        sym_meta = getattr(rule, "analyzer", {}).get("symbol") if rule else None
        if sym_meta:
            current_scope = self._current_scope
            assert current_scope is not None
            self._declare_from_node(node, sym_meta, current_scope)

        # 2. 进入新作用域（规则自声明，从 analyzer 配置读取）
        scope_meta = getattr(rule, "analyzer", {}).get("scope") if rule else None
        if scope_meta:
            name_attr = scope_meta.get("name_attr")
            if name_attr:
                name_val = getattr(node, name_attr, None)
                if isinstance(name_val, Node):
                    scope_name = getattr(name_val, "content", node.node_name)
                    self._scope_name_node_ids.add(id(name_val))
                elif name_val is not None:
                    scope_name = str(name_val)
                else:
                    scope_name = node.node_name
            else:
                scope_name = node.node_name
            kind = scope_meta.get("kind", "block")
            new_scope = Scope(name=scope_name, kind=kind, parent=scope)
            scope.children.append(new_scope)
            self._current_scope = new_scope
            scope = new_scope

        # 3. 解析标识符引用（规则自声明，从 analyzer 配置读取）
        if rule and getattr(rule, "analyzer", {}).get("identifier_ref", False):
            iref = getattr(rule, "analyzer", {}).get("identifier_ref")
            if isinstance(iref, str):
                self._resolve_identifier(node, scope, attr=iref)
            else:
                self._resolve_identifier(node, scope)

        # 4. 递归子节点
        for child in node.iter_children():
            self._walk(child)

        # 5. 退出作用域
        if scope_meta:
            self._current_scope = scope.parent
            assert self._current_scope is not None

    # 常量求值（位宽计算、符号值折叠等）已移至 transform/post/plugins/ 可选插件

    # ---- 符号声明 ----

    def _declare_from_node(self, node: Node, sym_rule: dict, scope: Scope) -> None:
        kind: str = sym_rule.get("kind", "unknown")
        name_attr = sym_rule.get("name_attr")
        if not name_attr:
            return

        # capture 配置：将节点属性提取到符号的 attrs 中
        # 格式: capture = { attr_name = "source_path", ... }
        # 例如: capture = { ports = "ports" } → 将 node.ports 存入 sym.attrs["ports"]
        capture = sym_rule.get("capture", {})

        names = self._extract_names(node, name_attr)
        for name in names:
            if not name:
                continue

            if name in scope.symbols:
                self._errors.append(f"重复声明 '{name}' 在作用域 '{scope.name}'")
                continue

            # 提取 capture 数据（可递归，产出纯 JSON 可序列化的结构）
            attrs: dict = {}

            def _capture_val(val: Any) -> Any:
                """将 Node 属性递归提取为 JSON 可序列化的值"""
                if val is None:
                    return None
                if isinstance(val, (str, int, float, bool)):
                    return val
                if isinstance(val, Node):
                    # 优先取主要值（content/name/value）
                    for p in ("content", "name", "value"):
                        pv = getattr(val, p, None)
                        if pv is not None and isinstance(pv, str):
                            return pv
                    # 否则递归提取所有非私有属性
                    d: dict = {}
                    for sub_attr in vars(val):
                        if sub_attr.startswith("_"):
                            continue
                        sv = _capture_val(getattr(val, sub_attr))
                        if sv is not None:
                            d[sub_attr] = sv
                    return d if d else None
                if isinstance(val, list):
                    items = [_capture_val(v) for v in val]
                    items = [v for v in items if v is not None]
                    return items if items else None
                return str(val)

            for attr_name, source_path in capture.items():
                captured = list(self._walk_path(node, source_path))
                if captured:
                    values = [_capture_val(v) for v in captured]
                    values = [v for v in values if v is not None]
                    if values:
                        attrs[attr_name] = values if len(values) > 1 else values[0]

            # capture 后处理器：由 [RuleName.analyzer] capture_hooks = [...] 触发
            hooks = sym_rule.get("capture_hooks", [])
            if isinstance(hooks, str):
                hooks = [hooks]
            for hook_name in hooks:
                hook = _capture_hooks.get(hook_name)
                if hook:
                    attrs = hook(node, sym_rule, scope, name, attrs) or attrs

            sym = scope.declare(name=name, kind=kind, decl_node=node, attrs=attrs)
            self._all_symbols.append(sym)

            # 收集语义映射（根据 _analyzer.toml 配置，懒初始化表结构）
            self._apply_mappings(kind, name, scope, attrs)

    # ---- 语义映射收集（由 _analyzer.toml 驱动）----

    def _apply_mappings(self, kind: str, name: str, scope: Scope, attrs: dict) -> None:
        """根据 _analyzer.toml 的 mapping 配置收集语义映射数据。"""
        if not self._mapping_config:
            return
        for entry in self._mapping_config:
            trigger = entry.get("trigger", {})
            if trigger.get("kind") != kind:
                continue
            table = entry.get("table", "")
            if not table:
                continue
            if table not in self._semantic_mapping:
                self._semantic_mapping[table] = {}

            # 构建映射键
            key_template = entry.get("key", "")
            ctx = {"scope.name": scope.name, "name": name}
            key = key_template
            for k, v in ctx.items():
                key = key.replace("{" + k + "}", str(v))

            # 提取源数据
            source_cfg = entry.get("source", {})
            source_data = attrs.get(source_cfg.get("attr", ""), [])
            if not isinstance(source_data, list):
                source_data = [source_data] if source_data else []

            # 筛选
            filter_cfg = source_cfg.get("filter", {})
            if filter_cfg:
                filtered = []
                for item in source_data:
                    if isinstance(item, dict) and all(
                        item.get(k) == v for k, v in filter_cfg.items()
                    ):
                        filtered.append(item)
                source_data = filtered

            # 按 items 逐项处理
            if source_cfg.get("items", False):
                items = []
                values = []
                for item in source_data:
                    if not isinstance(item, dict):
                        continue
                    fields = entry.get("fields", {})
                    if fields:
                        records = [{}]
                        for field_name, field_template in fields.items():
                            field_str = str(field_template)
                            if field_str.startswith("{$.") and field_str.endswith("}"):
                                field_key = field_str[3:-1]
                                val = item.get(field_key, field_str)
                                for r in records:
                                    r[field_name] = val
                            elif "[*]" in field_str:
                                val = item
                                for part in field_str.replace("[*]", "").split("."):
                                    part = part.strip()
                                    if isinstance(val, dict):
                                        val = val.get(part, {})
                                    elif isinstance(val, list):
                                        names = []
                                        for v in val:
                                            if isinstance(v, dict):
                                                n = v.get(part, "")
                                                if n:
                                                    names.append(n)
                                            elif isinstance(v, str):
                                                names.append(v)
                                        val = names
                                    else:
                                        val = {}
                                if isinstance(val, list):
                                    # 列表值：为每个值创建一条独立记录
                                    new_records = []
                                    for single_val in val:
                                        for r in records:
                                            nr = dict(r)
                                            nr[field_name] = single_val
                                            new_records.append(nr)
                                    records = new_records
                                else:
                                    for r in records:
                                        r[field_name] = val if val else field_str
                            else:
                                for r in records:
                                    r[field_name] = field_str
                        items.extend(records)
                    # value 简写：直接取 item 的某字段
                    value_key = entry.get("value", "")
                    if value_key:
                        values.append(item.get(value_key, ""))
                if items:
                    # 嵌套 key 展开："spi.master" → {spi: {master: items}}
                    self._set_nested(self._semantic_mapping[table], key, items)
                if values:
                    self._set_nested(self._semantic_mapping[table], key,
                                     values[0] if len(values) == 1 else values)

            # first_only：只取第一个匹配
            if entry.get("first_only"):
                # 已在上面的 items 循环中处理
                pass

    def _set_nested(self, d: dict, key: str, value: Any) -> None:
        """将 "spi.master" 展开为 {spi: {master: value}} 存入 dict"""
        parts = key.split(".")
        parent = d
        for p in parts[:-1]:
            parent = parent.setdefault(p, {})
        parent[parts[-1]] = value

    # ---- 路径遍历（共享 _walk_path / _extract_names）----

    @staticmethod
    def _walk_path(node: Node, path: str) -> Any:
        """沿点号路径遍历节点属性，逐层 yield。

        遇到 list → 展开每个元素继续遍历；
        遇到 Node → getattr；
        其他类型 → 终止。
        """
        parts = path.split(".")
        stack: list = [(node, 0)]
        while stack:
            val, idx = stack.pop()
            if idx >= len(parts):
                yield val
                continue
            p = parts[idx]
            if isinstance(val, Node):
                child = getattr(val, p, None)
                if child is not None:
                    stack.append((child, idx + 1))
            elif isinstance(val, list):
                for item in reversed(val):
                    stack.append((item, idx))
            else:
                return

    def _extract_names(self, node: Node, name_attr: str) -> list[str]:
        """从节点属性中提取符号名列表，支持列表属性（如 items）"""
        names: list[str] = []
        for val in SemanticAnalyzer._walk_path(node, name_attr):
            name = self._resolve_name_value(val)
            if name:
                names.append(name)
        if not names and isinstance(
            val := getattr(node, name_attr.split(".")[0], None), list
        ):
            # 兜底：尾部是列表，尝试从各元素提取名称
            fallback_attrs = ["param_name", "name"]
            for item in val:
                if isinstance(item, Node):
                    for attr_name in fallback_attrs:
                        n = getattr(item, attr_name, None)
                        if n:
                            name = self._resolve_name_value(n)
                            if name:
                                names.append(name)
                                break
        return names

    def _resolve_name_value(self, val: Any) -> Optional[str]:
        """将值解析为符号名字符串"""
        if val is None:
            return None
        if isinstance(val, Node):
            return getattr(val, "content", getattr(val, "value", None))
        if isinstance(val, str):
            return val
        return str(val) if val is not None else None

    # ---- 标识符解析 ----

    def _resolve_identifier(self, node: Node, scope: Scope, attr: str | None = None) -> None:
        # 跳过作用域定义名自身的 Identifier（如模块名、函数名）
        if id(node) in self._scope_name_node_ids:
            return
        if attr:
            # 从指定属性提取引用名（如 TypedTypeSpec 的 type_name）
            name = getattr(node, attr, None)
            if isinstance(name, Node):
                name = getattr(name, "content", str(name))
        else:
            name = getattr(node, "content", None) or getattr(node, "name", None)
        if not name:
            return
        sym = scope.resolve(name)
        if sym is not None:
            node.add_attr("_symbol_ref", sym)
        elif attr:
            # 指定属性名时：找不到符号则记录未解析引用
            msg = f"未解析的{attr}引用: '{name}' (节点: {node.node_name})"
            self._unresolved_refs.append(f"{node.node_name}.{attr}: '{name}'")
            print(f"[analyzer] WARN {msg}")
