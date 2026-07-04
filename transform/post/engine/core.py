"""
engine.py — ConfigDrivenTransform 插件

核心变换引擎，作为 TransformPlugin 注册到 AstTransformer 管线。
所有变换操作（expand/replace/delete/custom/扩展）都是注册的原语，
由 registry.py 的 register_primitive 统一管理。
"""

from typing import Any, Optional, Callable
from core.define import Node
from analyzer.scope import Scope
from transform.post.ast_transformer import TransformPlugin
from .registry import (
    TransformResult,
    TransformContext,
    SKIP,
    register_primitive,
    get_primitive,
    get_handler,
)
from .primitives import (
    lookup as _lookup,
    lookup_scope as _lookup_scope,
    lookup_type_scope as _lookup_type_scope,
    foreach as _foreach,
    emit as _emit,
)


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
        tables: Optional[dict] = None,
        extra: Optional[dict] = None,
    ):
        self._rules = rules
        self._extra = extra or {}

        # 从规则 TOML 的 [RuleName.transform] 提取变换配置
        self._configs = {
            name: transform
            for name, rule in rules.items()
            if isinstance((transform := getattr(rule, "transform", None)), dict)
        }
        self._tables = tables or {}

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

    def set_tables(self, tables: dict) -> None:
        """注入运行期映射表（分析器产出的语义映射）"""
        self._tables = tables

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

        # 条件守卫
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
        prim = get_primitive(kind)
        if prim is not None:
            result = prim(self, node, config, root_scope)
            if result is None:
                self._stats["delete"] += 1
            elif result is not SKIP:
                self._stats[kind] = self._stats.get(kind, 0) + 1
            else:
                self._stats["skipped"] += 1
            return result

        # 未知 kind → 跳过
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


# ============================================================
# 内置原语注册（模块级，import 时自动注册）
# ============================================================


def _expand_primitive(engine, node, config, root_scope):
    """expand 原语：lookup + foreach + emit"""
    from .primitives import make_exists_condition

    context = engine._build_context(node)

    source_cfg = config.get("source", {})
    lookup_source = source_cfg.get("lookup", "")
    lookup_key = source_cfg.get("key", "")

    data = None
    if lookup_source == "scope":
        data = _lookup_scope(root_scope, lookup_key, context) if lookup_key else None
    elif lookup_source == "scope_type":
        data = (
            _lookup_type_scope(root_scope, lookup_key, context) if lookup_key else None
        )
    elif lookup_source:
        table = engine._tables.get(lookup_source, {})
        data = _lookup(table, lookup_key, context) if lookup_key else None

    foreach_field = config.get("foreach", "")
    as_name = config.get("as", foreach_field)
    items: list = []
    if data and foreach_field:
        if isinstance(data, dict) and foreach_field in data:
            raw_items = data[foreach_field]
            items = raw_items if isinstance(raw_items, list) else [raw_items]
        elif isinstance(data, list):
            items = data
            as_name = foreach_field or "item"
    elif data and not foreach_field:
        if isinstance(data, dict):
            context.update(data)

    # items_path 嵌套拍平：遍历 items 中每个元素，沿点号路径取出子列表展开
    # 例如 items_path = "items.items" → 对每个 port 取出 port["items"]["items"] 列表
    flatten_path = config.get("items_path", "")
    if flatten_path and items:
        flat: list = []
        for item in items:
            cur = item
            for part in flatten_path.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    cur = None
                    break
            if isinstance(cur, list):
                # 将子列表元素展开到主列表，同时保留外层 context 属性
                for sub in cur:
                    if isinstance(sub, dict):
                        merged = dict(item if isinstance(item, dict) else {})
                        merged.update(sub)
                        flat.append(merged)
                    else:
                        flat.append(sub)
            elif cur is not None:
                flat.append(cur)
        items = flat

    emit_spec = config.get("emit")
    if emit_spec is None:
        return SKIP

    if items:

        def _do_emit(item: Any, ctx: dict):
            return _emit(emit_spec, ctx)

        results = _foreach(items, as_name, _do_emit, context)
        return results if results else SKIP
    else:
        result = _emit(emit_spec, context)
        return result


def _replace_primitive(engine, node, config, root_scope):
    """replace 原语：用新节点替换当前节点"""
    context = engine._build_context(node)

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
    return _emit(emit_spec, context)


def _delete_primitive(engine, node, config, root_scope):
    """delete 原语：删除节点"""
    return None


def _custom_primitive(engine, node, config, root_scope):
    """custom 原语（向后兼容）：委托给旧式 handler"""
    handler_name = config.get("handler", "")
    if not handler_name:
        return SKIP

    handler = get_handler(handler_name)
    if handler is None:
        return SKIP

    try:
        result = handler(engine, node, config, root_scope)
        return result
    except Exception as e:
        print(f"  ❌ [transform] {node.node_name}: handler '{handler_name}' 异常: {e}")
        import traceback

        traceback.print_exc()
        return SKIP


# 统一注册到原语注册表
register_primitive("expand", _expand_primitive)
register_primitive("replace", _replace_primitive)
register_primitive("delete", _delete_primitive)
register_primitive("custom", _custom_primitive)
