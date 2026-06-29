"""
engine.py — ConfigDrivenTransform 插件

核心变换引擎，作为 TransformPlugin 注册到 AstTransformer 管线。

工作流程:
  1. 遍历 AST 节点
  2. 每个节点查找其规则名对应的 transform 配置
  3. 根据 config.kind 调度：
       "expand"   → 原语展开 (lookup + foreach + emit)
       "replace"  → 节点替换
       "delete"   → 节点删除
       "custom"   → 委托给已注册的 Python handler
  4. 返回变换结果

原语无法覆盖的场景 → 用 handler 兜底。
"""

from typing import Any, Optional, Callable
from core.define import Node
from analyzer.scope import Scope
from transform.post.ast_transformer import TransformPlugin
from .registry import (
    TransformContext,
    TransformResult,
    SKIP,
    get_handler,
)
from .primitives import (
    lookup as _lookup,
    lookup_scope as _lookup_scope,
    lookup_type_scope as _lookup_type_scope,
    foreach as _foreach,
    emit as _emit,
    resolve_attrs,
)
from .config_loader import load_transform_configs


class ConfigDrivenTransform(TransformPlugin):
    """配置驱动的 AST 变换插件

    用法:
        transformer = AstTransformer()
        transformer.register(ConfigDrivenTransform(
            rules=grammar_rules,
            ext_dir="grammar/rules_verilog_ext",
        ))
        ast = transformer.transform(ast, root_scope)
    """

    def __init__(
        self,
        rules: dict[str, Any],
        ext_dir: str = "",
        tables: Optional[dict] = None,
        extra: Optional[dict] = None,
    ):
        self._rules = rules
        self._extra = extra or {}

        # 加载 transform 配置和参考表
        if tables is not None:
            self._configs = {
                name: transform
                for name, rule in rules.items()
                if isinstance((transform := getattr(rule, "transform", None)), dict)
            }
            self._tables = tables
        else:
            self._configs, self._tables = load_transform_configs(rules, ext_dir)

        self._stats = {
            "expand": 0,
            "replace": 0,
            "delete": 0,
            "custom": 0,
            "skipped": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 AST 并执行所有匹配的变换"""
        self._stats = {
            "expand": 0,
            "replace": 0,
            "delete": 0,
            "custom": 0,
            "skipped": 0,
        }
        result = self._walk(ast, root_scope, parent=None, parent_attr=None)
        if result is SKIP or result is None:
            return ast
        if isinstance(result, list):
            return result[0] if result else ast
        assert isinstance(result, Node), f"预期 Node，实际 {type(result)}"
        return result

    # ── 递归遍历核心 ──

    def _walk(
        self,
        node: Any,
        root_scope: Scope,
        parent: Optional[Node],
        parent_attr: Optional[str],
    ) -> TransformResult:
        """递归遍历并变换 AST"""
        if isinstance(node, list):
            return self._walk_list(node, root_scope, parent, parent_attr)
        if not isinstance(node, Node):
            return node

        # 1. 先变换子节点（自底向上）
        self._transform_children(node, root_scope)

        # 2. 变换当前节点
        return self._apply_transform(node, root_scope, parent, parent_attr)

    def _walk_list(
        self,
        items: list,
        root_scope: Scope,
        parent: Optional[Node],
        parent_attr: Optional[str],
    ) -> list:
        """遍历列表，扁平化处理变换结果"""
        result: list = []
        for item in items:
            transformed = self._walk(item, root_scope, parent, parent_attr)
            if transformed is SKIP:
                result.append(item)
            elif transformed is None:
                continue  # 删除
            elif isinstance(transformed, list):
                result.extend(transformed)
            else:
                result.append(transformed)
        return result

    def _transform_children(self, node: Node, root_scope: Scope) -> None:
        """变换节点的所有子节点"""
        for attr_name in list(vars(node)):
            val = getattr(node, attr_name)
            if isinstance(val, Node):
                result = self._walk(val, root_scope, parent=node, parent_attr=attr_name)
                if result is SKIP:
                    pass
                elif result is None:
                    setattr(node, attr_name, None)
                elif isinstance(result, list):
                    setattr(node, attr_name, result[0] if result else None)
                else:
                    setattr(node, attr_name, result)
            elif isinstance(val, list):
                new_list: list = []
                for item in val:
                    if isinstance(item, Node):
                        r = self._walk(
                            item, root_scope, parent=node, parent_attr=attr_name
                        )
                        if r is SKIP:
                            new_list.append(item)
                        elif r is None:
                            continue
                        elif isinstance(r, list):
                            new_list.extend(r)
                        else:
                            new_list.append(r)
                    else:
                        new_list.append(item)
                setattr(node, attr_name, new_list)

    # ── 变换调度核心 ──

    def _apply_transform(
        self,
        node: Node,
        root_scope: Scope,
        parent: Optional[Node],
        parent_attr: Optional[str],
    ) -> TransformResult:
        """根据 transform 配置调度变换"""
        config = self._configs.get(node.node_name)
        if config is None:
            return SKIP

        # 条件守卫：所有 kind 统一检查
        condition_cfg = config.get("condition")
        if condition_cfg:
            context = self._build_context(node)
            from .primitives import make_exists_condition

            exists_path = condition_cfg.get("exists", "")
            if exists_path:
                pred = make_exists_condition(exists_path)
                if not pred(context):
                    self._stats["skipped"] += 1
                    return SKIP

        kind = config.get("kind", "")

        if kind == "custom":
            return self._apply_custom(node, root_scope, config)
        elif kind == "expand":
            return self._apply_expand(node, config, root_scope)
        elif kind == "replace":
            return self._apply_replace(node, config, root_scope)
        elif kind == "delete":
            return None
        else:
            # 未知 kind → 跳过
            return SKIP

    # ── 原语: expand ──

    def _apply_expand(self, node: Node, config: dict, root_scope: Scope) -> TransformResult:
        """expand 变换：lookup + foreach + emit

        配置格式:
            kind = "expand"
            source = { lookup = "type", key = "{attr}.{attr}" }
            foreach = "signals"
            as = "signal"
            emit = { node = "NodeName", direction = "{signal.direction}", ... }
            # 可选
            condition = { exists = "attr.path" }
        """
        # 构建上下文
        context = self._build_context(node)

        # source 查表（支持 type 表和 scope 符号表）
        source_cfg = config.get("source", {})
        lookup_source = source_cfg.get("lookup", "")
        lookup_key = source_cfg.get("key", "")

        data = None
        if lookup_source == "scope":
            data = _lookup_scope(root_scope, lookup_key, context) if lookup_key else None
        elif lookup_source == "scope_type":
            data = _lookup_type_scope(root_scope, lookup_key, context) if lookup_key else None
        elif lookup_source:
            table = self._tables.get(lookup_source, {})
            data = _lookup(table, lookup_key, context) if lookup_key else None

        # foreach 遍历
        #   foreach: 数据源字段名（从 lookup 结果中取哪个字段作为遍历列表）
        #   as:      迭代变量名（在 emit 模板中用 {变量名.xxx}，默认用 foreach 字段名）
        foreach_field = config.get("foreach", "")
        as_name = config.get("as", foreach_field)  # 默认与 foreach 字段同名
        items: list = []
        if data and foreach_field:
            if isinstance(data, dict) and foreach_field in data:
                raw_items = data[foreach_field]
                items = raw_items if isinstance(raw_items, list) else [raw_items]
            elif isinstance(data, list):
                items = data
                as_name = foreach_field or "item"
        elif data and not foreach_field:
            # 没有 foreach，用 data 本身作为 context 扩展
            if isinstance(data, dict):
                context.update(data)

        # emit 生成
        emit_spec = config.get("emit")
        if emit_spec is None:
            self._stats["skipped"] += 1
            return SKIP

        if items:
            # 有 foreach → 对每个 item emit
            def _do_emit(item: Any, ctx: dict) -> Optional[Node]:
                return _emit(emit_spec, ctx)

            results = _foreach(items, as_name, _do_emit, context)
            if results:
                self._stats["expand"] += 1
                return results
            return SKIP
        else:
            # 无 foreach → 直接 emit
            result = _emit(emit_spec, context)
            self._stats["expand"] += 1
            return result

    # ── 原语: replace ──

    def _apply_replace(self, node: Node, config: dict, root_scope: Scope) -> TransformResult:
        """replace 变换：用新节点替换当前节点

        配置格式:
            kind = "replace"
            source = { lookup = "scope", key = "{name}" }  # 可选：查符号表
            emit = { node = "NewNode", ... }
        """
        context = self._build_context(node)

        # 可选：先查 scope 表（替换时可能需要符号信息）
        source_cfg = config.get("source", {})
        lookup_source = source_cfg.get("lookup", "")
        lookup_key = source_cfg.get("key", "")
        if lookup_source == "scope" and lookup_key:
            scope_data = _lookup_scope(root_scope, lookup_key, context)
            if scope_data and isinstance(scope_data, dict):
                context.update(scope_data)

        emit_spec = config.get("emit")
        if emit_spec is None:
            return SKIP
        result = _emit(emit_spec, context)
        self._stats["replace"] += 1
        return result

    # ── custom handler ──

    def _apply_custom(
        self,
        node: Node,
        root_scope: Scope,
        config: dict,
    ) -> TransformResult:
        """custom 变换：委托给已注册的 Python handler"""
        handler_name = config.get("handler", "")
        if not handler_name:
            print(f"  ⚠️ [transform] {node.node_name}: kind=custom 但未指定 handler")
            return SKIP

        handler = get_handler(handler_name)
        if handler is None:
            print(f"  ⚠️ [transform] {node.node_name}: handler '{handler_name}' 未注册")
            return SKIP

        ctx = TransformContext(
            rule_name=node.node_name,
            config=config,
            tables=self._tables,
            extra=self._extra,
        )
        try:
            result = handler(node, root_scope, ctx)
            self._stats["custom"] += 1
            return result
        except Exception as e:
            print(
                f"  ❌ [transform] {node.node_name}: handler '{handler_name}' 异常: {e}"
            )
            import traceback

            traceback.print_exc()
            return SKIP

    # ── 辅助 ──

    def _build_context(self, node: Node) -> dict[str, Any]:
        """将节点的属性展开为扁平 context dict

        支持:
            node.foo              → context["foo"]
            node.sub.name         → context["sub.name"]
            node.sub_item         → context["sub_item"]  (快捷方式)

        快捷方式：若一个 Node 有 name/content/value 主要值属性，
        该属性的值会直接以 Node 名称为键注册（覆盖 Node 本身）。
        """
        ctx: dict[str, Any] = {}

        def _flatten(obj: Any, prefix: str = ""):
            if isinstance(obj, Node):
                # 主要值快捷方式：有 name/content/value 的 Node，
                # 直接用标量值以该 Node 的 key 注册
                has_primary = False
                for primary in ("name", "content", "value"):
                    if hasattr(obj, primary):
                        pv = getattr(obj, primary)
                        if isinstance(pv, str):
                            base_key = prefix.rstrip(".") if prefix else ""
                            if base_key:
                                ctx[base_key] = pv
                                has_primary = True
                            elif not prefix:
                                # 根节点：直接用属性名注册
                                ctx[primary] = pv
                                has_primary = True
                            break

                # 无论是否有快捷方式，都展开子属性（sub_node 等）
                # 跳过 name/content/value，因为它们已由快捷方式处理
                for attr_name in vars(obj):
                    if attr_name.startswith("_") or attr_name in (
                        "name",
                        "content",
                        "value",
                    ):
                        continue
                    val = getattr(obj, attr_name)
                    key = f"{prefix}{attr_name}" if prefix else attr_name
                    if isinstance(val, (Node, dict)):
                        ctx[key] = val
                        _flatten(val, key + ".")
                    elif isinstance(val, list):
                        ctx[key] = val
                        for i, item in enumerate(val):
                            if isinstance(item, (Node, dict)):
                                ctx[f"{key}[{i}]"] = item
                                _flatten(item, f"{key}[{i}].")
                            else:
                                ctx[f"{key}[{i}]"] = item
                    else:
                        ctx[key] = val

                # 如果没有快捷方式，把 Node 自身也注册（用于路径访问）
                if not has_primary:
                    base_key = prefix.rstrip(".") if prefix else ""
                    if base_key and base_key not in ctx:
                        ctx[base_key] = obj
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}{k}" if prefix else k
                    ctx[key] = v
                    if isinstance(v, (Node, dict)):
                        _flatten(v, key + ".")
                    elif isinstance(v, list):
                        for i, item in enumerate(v):
                            if isinstance(item, (Node, dict)):
                                ctx[f"{key}[{i}]"] = item
                                _flatten(item, f"{key}[{i}].")

        _flatten(node)

        # 额外注入
        ctx["_node"] = node
        return ctx
