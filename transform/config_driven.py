"""
config_driven.py — ConfigDrivenTransform 插件

核心变换引擎，作为 TransformPlugin 注册到 AstTransformer 管线。
所有变换操作（expand/replace/delete/扩展）都是注册的原语，
由 primitives/registry.py 的 register_primitive 统一管理。
Doc: docs/language_walkthrough.md（配置驱动变换）
"""

from typing import Any
from core.define import Node
from analyzer.scope import Scope
from .engine import TransformPlugin, AstTransformer, register_plugin
from .primitives.registry import (
    TransformResult,
    SKIP,
    register_primitive,
    get_primitive,
)
from .primitives.template import resolve_template
from .primitives.lookup import (
    lookup as _lookup,
    lookup_scope as _lookup_scope,
    lookup_child_scope as _lookup_child_scope,
)
from .primitives.flow import foreach as _foreach
from .primitives.node import emit as _emit


@register_plugin
class ConfigDrivenTransform(TransformPlugin):
    """配置驱动的 AST 变换插件

    用法:
        AstTransformer.set_shared("rules", grammar_rules)
        transformer = AstTransformer()
        ast = transformer.transform(ast, root_scope)
    """

    def __init__(
        self,
        rules: dict[str, Any] | None = None,
        tables: dict | None = None,
        extra: dict | None = None,
    ):
        if rules is None:
            rules = AstTransformer._shared_ctx.get("rules", {})
        self._rules = rules
        self._extra = extra or {}

        # 从规则 TOML 的 [RuleName.transform] 提取变换配置
        assert rules is not None
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
            "skipped": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 AST 并执行所有匹配的变换"""
        # 自动拉取 SemanticMappingPlugin 的映射表
        if self._transformer:
            for plugin in self._transformer.plugins:
                if type(plugin).__name__ == "SemanticMappingPlugin":
                    self._tables = plugin.tables  # type: ignore[attr-defined]
                    break

        self._stats = {
            "expand": 0,
            "replace": 0,
            "delete": 0,
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
        parent: Node | None,
        parent_attr: str | None,
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
        parent: Node | None,
        parent_attr: str | None,
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
        parent: Node | None,
        parent_attr: str | None,
    ) -> TransformResult:
        """根据 transform 配置调度变换"""
        del parent, parent_attr  # 调用链透传参数，本方法不消费
        config = self._configs.get(node.node_name)
        if config is None:
            return SKIP

        # 条件守卫
        condition_cfg = config.get("condition")
        if condition_cfg:
            context = self._build_context(node)
            from .primitives.flow import make_exists_condition

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
                # 已注册为快捷方式的 name/content/value 跳过重复展开
                for attr_name in vars(obj):
                    if attr_name.startswith("_"):
                        continue
                    if attr_name in ("name", "content", "value") and has_primary:
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


# ── 内置原语注册（模块级，import 时自动注册）──


def _expand_primitive(engine, node, config, root_scope):
    """expand 原语：lookup + foreach + emit

    消费 type_ports_flat 表（含常规端口 + _apply_refs 展开的回调端口），
    对每条扁平端口 { direction, name } 做 foreach → switch → emit AST 节点。

    数据流：
        type_ports_flat["spi"]["slave"] = [
            { "direction": "output", "name": "miso" },   # 常规端口
            { "direction": "input",  "name": "clk" },    # 来自 _apply_refs
            ...
        ]
        ↓
        foreach → {direction} → switch → emit AnsiInputDecl/AnsiOutputDecl
        ↓
        AST 节点追加到模块端口列表
    """
    context = engine._build_context(node)

    source_cfg = config.get("source", {})
    lookup_source = source_cfg.get("lookup", "")
    lookup_key = source_cfg.get("key", "")

    data = None
    if lookup_source == "scope":
        # 支持 scope_kind 参数：按 kind 查找子作用域再解析符号
        scope_kind = source_cfg.get("scope_kind")
        if scope_kind:
            data = (
                _lookup_child_scope(root_scope, lookup_key, scope_kind, context)
                if lookup_key
                else None
            )
        else:
            data = (
                _lookup_scope(root_scope, lookup_key, context) if lookup_key else None
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

        def _do_transform(item: Any, ctx: dict):
            """对 foreach 元素执行变换：emit 或原语调度"""
            del item  # foreach 回调协议签名参数，本实现从 ctx 取元素
            if isinstance(emit_spec, dict) and "kind" in emit_spec:
                prim = get_primitive(emit_spec["kind"])
                if prim:
                    # 将 foreach 上下文注到节点上供原语消费
                    saved = {}
                    try:
                        for k, v in ctx.items():
                            # foreach 的 item 存在 $ 下，展开到节点顶层
                            if k == "$" and isinstance(v, dict):
                                for ik, iv in v.items():
                                    if not hasattr(node, ik):
                                        setattr(node, ik, iv)
                                        saved[ik] = None
                            elif not hasattr(node, k):
                                setattr(node, k, v)
                                saved[k] = None
                            elif getattr(node, k) != v:
                                saved[k] = getattr(node, k)
                                setattr(node, k, v)
                        return prim(engine, node, emit_spec, root_scope)
                    finally:
                        for k, v_orig in saved.items():
                            if v_orig is None:
                                delattr(node, k)
                            else:
                                setattr(node, k, v_orig)
            return _emit(emit_spec, ctx)

        results = _foreach(items, as_name, _do_transform, context)
        # 兜底防御：SKIP（switch 无匹配分支等"无产出"哨兵）不应并入结果列表
        # 泄漏进 AST（会渲染成字面 "SKIP"）；此处过滤与 _walk 的 SKIP 语义
        # （保留原节点）不同——foreach 的原节点已被消费，SKIP = 该行无产出。
        results = [r for r in results if r is not SKIP]
        return results if results else SKIP
    else:
        if isinstance(emit_spec, dict) and "kind" in emit_spec:
            prim = get_primitive(emit_spec["kind"])
            if prim:
                return prim(engine, node, emit_spec, root_scope)
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
    if isinstance(emit_spec, dict) and "kind" in emit_spec:
        prim = get_primitive(emit_spec["kind"])
        if prim:
            return prim(engine, node, emit_spec, root_scope)
    return _emit(emit_spec, context)


def _delete_primitive(engine, node, config, root_scope):
    """delete 原语：删除节点"""
    del engine, node, config, root_scope  # 原语注册协议签名参数，本原语无操作
    return None


# 统一注册到原语注册表
register_primitive("expand", _expand_primitive)
register_primitive("replace", _replace_primitive)
register_primitive("delete", _delete_primitive)


# ── emit 原语：创建 AST 节点 ──


def _emit_primitive(engine, node, config, root_scope):
    """emit 原语：根据规格创建 AST 节点。"""
    del root_scope  # 原语注册协议签名参数，本原语不消费
    context = engine._build_context(node)
    result = _emit(config, context)
    return result if result is not None else SKIP


register_primitive("emit", _emit_primitive)


# ── switch 原语：按条件分支调度不同变换 ──


def _switch_primitive(engine, node, config, root_scope):
    """switch 原语：按条件分支调度不同变换。

    配置格式:
        kind = "switch"
        on = "{attr}"       # 模板表达式，被求值作为分支键
        cases.val1 = { kind = "emit", node = "...", ... }
        cases.val2 = { kind = "expand", ... }
        default = { ... }   # 可选兜底，无 kind 时作为 emit 规格
    """
    context = engine._build_context(node)
    on_expr = config.get("on", "")
    value = resolve_template(on_expr, context)
    if value == on_expr:
        return SKIP

    cases = config.get("cases", {})
    sub_config = cases.get(value) or config.get("default")
    if sub_config is None:
        return SKIP

    kind = sub_config.get("kind", "")
    if kind:
        prim = get_primitive(kind)
        if prim:
            result = prim(engine, node, sub_config, root_scope)
            if result is not SKIP:
                engine._stats["switch"] = engine._stats.get("switch", 0) + 1
            return result
    else:
        # 无 kind → 直接作为 emit 规格
        ctx = engine._build_context(node)
        result = _emit(sub_config, ctx)
        if result is not None:
            engine._stats["switch"] = engine._stats.get("switch", 0) + 1
            return result
    return SKIP


register_primitive("switch", _switch_primitive)
