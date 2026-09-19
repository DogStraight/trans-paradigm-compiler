"""
config_driven.py — ConfigDrivenTransform 插件

核心变换引擎，作为 TransformPlugin 注册到 AstTransformer 管线。
所有变换操作（expand/replace/delete/扩展）都是注册的原语，
由 primitives/registry.py 的 register_primitive 统一管理。
Doc: docs/language_walkthrough.md（配置驱动变换）
"""

from contextlib import contextmanager
from functools import partial
from typing import Any
from core.define import Node
from analyzer.scope import Scope
from .engine import TransformPlugin, AstTransformer, register_plugin, migrate_comments
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


@register_plugin(requires=["mapping_tables"])
class ConfigDrivenTransform(TransformPlugin):
    """配置驱动的 AST 变换插件

    消费语义映射表（`SemanticMappingPlugin` 产出）——契约声明
    `requires=["mapping_tables"]`（ADR-0015 §3：插件级声明，引擎只做机械核验；
    **时点不在插件侧**，由管线配置编排）。

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
        # 映射表按契约名（`requires=["mapping_tables"]`）从共享产物通道取用：
        # 生产方（SemanticMappingPlugin）经 note_produced 发布，调度按单元时点
        # 累积——故本插件不依赖"与生产方同实例"，插件级单元下同样成立。
        produced = AstTransformer._shared_ctx.get("productions") or {}
        tables = produced.get("mapping_tables")
        if tables is not None:
            self._tables = tables

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
        return migrate_comments(ast, result)

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
                # 分裂（1:N）：注释迁移到第一个产物（跟随替换位置）
                migrated = [
                    migrate_comments(item, t) if i == 0 else t
                    for i, t in enumerate(transformed)
                ]
                result.extend(migrated)
            else:
                # 1:1 替换：新节点继承被替换节点的注释（变换路径注释随结构走）
                result.append(migrate_comments(item, transformed))
        return result

    def _transform_children(self, node: Node, root_scope: Scope) -> None:
        """变换节点的所有子节点（单节点属性 / 列表属性两路）。"""
        for attr_name in list(vars(node)):
            val = getattr(node, attr_name)
            if isinstance(val, Node):
                self._replace_child_attr(node, attr_name, val, root_scope)
            elif isinstance(val, list):
                setattr(
                    node,
                    attr_name,
                    self._transform_child_list(val, node, attr_name, root_scope),
                )

    def _replace_child_attr(
        self, node: Node, attr_name: str, val: Node, root_scope: Scope
    ) -> None:
        """单节点属性：SKIP → 原样；None → 置 None；列表结果 → 取首项（注释并入首项）。"""
        result = self._walk(val, root_scope, parent=node, parent_attr=attr_name)
        if result is SKIP:
            return
        if result is None:
            setattr(node, attr_name, None)
            return
        merged = _migrated_results(val, result)
        setattr(node, attr_name, merged[0] if merged else None)

    def _transform_child_list(
        self, val: list, node: Node, attr_name: str, root_scope: Scope
    ) -> list:
        """列表属性：逐项走 walk——SKIP 保留原项、None 丢弃、列表结果展开。"""
        new_list: list = []
        for item in val:
            if not isinstance(item, Node):
                new_list.append(item)
                continue
            r = self._walk(item, root_scope, parent=node, parent_attr=attr_name)
            if r is SKIP:
                new_list.append(item)
            elif r is None:
                continue
            else:
                new_list.extend(_migrated_results(item, r))
        return new_list

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
        展开规则见 `_flatten_context` / `_flatten_node` / `_flatten_dict`。
        """
        ctx: dict[str, Any] = {}
        _flatten_context(node, ctx)
        # 额外注入
        ctx["_node"] = node
        return ctx


# 主要值属性（Node 有其一且为字符串时，以该 Node 的 key 注册标量而非 Node 本身）
_PRIMARY_ATTRS = ("name", "content", "value")


def _migrated_results(orig: Node, result: Any) -> list:
    """walk 结果（非 SKIP）→ 节点列表：列表结果逐项（注释并入首项），单节点包一层。"""
    if isinstance(result, list):
        return [
            migrate_comments(orig, t) if i == 0 else t
            for i, t in enumerate(result)
        ]
    return [migrate_comments(orig, result)]


def _flatten_context(obj: Any, ctx: dict, prefix: str = "") -> None:
    """把 obj（Node / dict）的属性展开进 ctx（点号前缀 + `key[i]` 列表下标）。"""
    if isinstance(obj, Node):
        _flatten_node(obj, ctx, prefix)
    elif isinstance(obj, dict):
        _flatten_dict(obj, ctx, prefix)


def _flatten_node(obj: Node, ctx: dict, prefix: str) -> None:
    """Node → ctx：主值快捷方式 + 子属性展开 + 无快捷方式时注册 Node 自身。"""
    has_primary = _register_primary(obj, ctx, prefix)
    for attr_name in vars(obj):
        if attr_name.startswith("_"):
            continue
        if attr_name in _PRIMARY_ATTRS and has_primary:
            continue
        key = f"{prefix}{attr_name}" if prefix else attr_name
        _flatten_value(key, getattr(obj, attr_name), ctx)
    if has_primary:
        return
    # 无快捷方式：把 Node 自身也注册（用于路径访问）
    base_key = prefix.rstrip(".") if prefix else ""
    if base_key and base_key not in ctx:
        ctx[base_key] = obj


def _register_primary(obj: Node, ctx: dict, prefix: str) -> bool:
    """主值快捷方式：以该 Node 的 key（根节点则用属性名）注册字符串主值。

    返回是否注册了快捷方式——它决定子属性展开是否跳过 `name/content/value`、
    以及是否还需把 Node 自身注册进 ctx。
    """
    for primary in _PRIMARY_ATTRS:
        if not hasattr(obj, primary):
            continue
        pv = getattr(obj, primary)
        if not isinstance(pv, str):
            continue
        base_key = prefix.rstrip(".") if prefix else ""
        if base_key or not prefix:
            ctx[base_key or primary] = pv
            return True
        return False  # 前缀只余点号（不可达）：不注册，也不认快捷方式
    return False


def _flatten_value(key: str, val: Any, ctx: dict) -> None:
    """Node 的单个属性值展开：Node/dict → 注册 + 递归；list → 注册 + 逐下标。"""
    ctx[key] = val
    if isinstance(val, (Node, dict)):
        _flatten_context(val, ctx, key + ".")
    elif isinstance(val, list):
        for i, item in enumerate(val):
            ctx[f"{key}[{i}]"] = item
            if isinstance(item, (Node, dict)):
                _flatten_context(item, ctx, f"{key}[{i}].")


def _flatten_dict(obj: dict, ctx: dict, prefix: str) -> None:
    """dict → ctx：逐键注册（Node/dict 递归；list 只对复合元素记下标）。"""
    for k, v in obj.items():
        key = f"{prefix}{k}" if prefix else k
        ctx[key] = v
        if isinstance(v, (Node, dict)):
            _flatten_context(v, ctx, key + ".")
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, (Node, dict)):
                    ctx[f"{key}[{i}]"] = item
                    _flatten_context(item, ctx, f"{key}[{i}].")


# ── 内置原语注册（模块级，import 时自动注册）──


def _expand_primitive(engine, node, config, root_scope):
    """expand 原语：lookup + foreach + emit

    消费 type_ports_flat 表（组件 postpass 展开的完整端口集，经 resolved_ports
    注入），对每条扁平端口 { direction, name } 做 foreach → switch → emit AST
    节点。

    数据流：
        type_ports_flat["spi"]["slave"] = [
            { "direction": "output", "name": "miso" },
            { "direction": "input",  "name": "clk" },    # 嵌套/对侧已含（前缀化）
            ...
        ]
        ↓
        foreach → {direction} → switch → emit AnsiInputDecl/AnsiOutputDecl
        ↓
        AST 节点追加到模块端口列表
    """
    context = engine._build_context(node)
    data = _resolve_expand_source(
        engine, config.get("source", {}), root_scope, context
    )
    items, as_name = _extract_expand_items(config, data, context)
    items = _flatten_items_path(items, config.get("items_path", ""))

    emit_spec = config.get("emit")
    if emit_spec is None:
        return SKIP
    if not items:
        return _run_emit_once(engine, node, emit_spec, root_scope, context)

    results = _foreach(
        items,
        as_name,
        partial(_expand_item, engine, node, emit_spec, root_scope),
        context,
    )
    # 兜底防御：SKIP（switch 无匹配分支等"无产出"哨兵）不应并入结果列表
    # 泄漏进 AST（会渲染成字面 "SKIP"）；此处过滤与 _walk 的 SKIP 语义
    # （保留原节点）不同——foreach 的原节点已被消费，SKIP = 该行无产出。
    results = [r for r in results if r is not SKIP]
    return results if results else SKIP


def _resolve_expand_source(engine, source_cfg: dict, root_scope, context) -> Any:
    """按 `source` 声明取源数据：scope（可带 `scope_kind`）/ 映射表；无声明 → None。"""
    lookup_source = source_cfg.get("lookup", "")
    lookup_key = source_cfg.get("key", "")
    if not lookup_source:
        return None
    if not lookup_key:
        return None
    if lookup_source == "scope":
        # scope_kind：按 kind 查找子作用域再解析符号
        scope_kind = source_cfg.get("scope_kind")
        if scope_kind:
            return _lookup_child_scope(root_scope, lookup_key, scope_kind, context)
        return _lookup_scope(root_scope, lookup_key, context)
    return _lookup(engine._tables.get(lookup_source, {}), lookup_key, context)


def _extract_expand_items(config: dict, data: Any, context: dict) -> tuple[list, str]:
    """`foreach` 声明 → `(待展开元素列表, 元素绑定名)`。

    - 数据是 dict 且含 foreach 字段 → 取该字段（非列表则单元素包一层）；
    - 数据本身就是列表 → 整表即元素列表，绑定名回退 `item`；
    - 无 foreach 字段而数据是 dict → 直接并入 context（不展开元素）。
    """
    foreach_field = config.get("foreach", "")
    as_name = config.get("as", foreach_field)
    if not data or not foreach_field:
        if data and isinstance(data, dict):
            context.update(data)
        return [], as_name
    if isinstance(data, dict) and foreach_field in data:
        raw_items = data[foreach_field]
        return (raw_items if isinstance(raw_items, list) else [raw_items]), as_name
    if isinstance(data, list):
        return data, foreach_field or "item"
    return [], as_name


def _flatten_items_path(items: list, flatten_path: str) -> list:
    """`items_path` 嵌套拍平：沿点号路径取子列表并展开，保留外层属性。

    例：`items_path = "items.items"` → 对每个 port 取 `port["items"]["items"]`
    列表，子元素与外层属性合并后展开到主列表。
    """
    if not flatten_path or not items:
        return items
    flat: list = []
    for item in items:
        flat.extend(_expand_path_entry(item, _path_get(item, flatten_path)))
    return flat


def _expand_path_entry(item: Any, cur: Any) -> list:
    """`items_path` 取到值后的展开。

    列表 → 逐元素（dict 与外层属性合并）；其它非 None → 该值单元素；None → 空。
    """
    if isinstance(cur, list):
        return [_merge_parent(item, sub) for sub in cur]
    return [] if cur is None else [cur]


def _merge_parent(item: Any, sub: Any) -> Any:
    """子元素与外层属性合并；子元素非 dict → 原样保留（不造新 dict）。"""
    if not isinstance(sub, dict):
        return sub
    merged = dict(item) if isinstance(item, dict) else {}
    merged.update(sub)
    return merged


def _path_get(item: Any, path: str) -> Any:
    """沿点号路径取值；中途非 dict → None。"""
    cur = item
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@contextmanager
def _injected_foreach_context(node: Node, ctx: dict):
    """临时把 foreach 上下文注到节点上供原语消费，退出还原。

    `ctx["$"]` 是本次 foreach 元素（作为 dict 展开到节点顶层）；其余键直接注入。
    原本不在节点上的属性记录为 None → 退出删除；已存在的同名属性记原值 → 退出还原
    （值不同才覆盖，相同不动）。
    """
    saved: dict[str, Any] = {}
    try:
        for k, v in ctx.items():
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
        yield
    finally:
        for k, v_orig in saved.items():
            if v_orig is None:
                delattr(node, k)
            else:
                setattr(node, k, v_orig)


def _run_emit_once(engine, node, emit_spec, root_scope, context) -> Any:
    """无 foreach 元素时的单次产出：emit 声明带 `kind` → 原语；否则 `_emit`。"""
    if isinstance(emit_spec, dict) and "kind" in emit_spec:
        prim = get_primitive(emit_spec["kind"])
        if prim:
            return prim(engine, node, emit_spec, root_scope)
    return _emit(emit_spec, context)


def _expand_item(engine, node, emit_spec, root_scope, item, ctx):
    """foreach 回调：对元素执行 emit 或原语调度（签名由 `_foreach` 协议约定）。"""
    del item  # foreach 回调协议签名参数，本实现从 ctx 取元素
    if isinstance(emit_spec, dict) and "kind" in emit_spec:
        prim = get_primitive(emit_spec["kind"])
        if prim:
            # 将 foreach 上下文注到节点上供原语消费
            with _injected_foreach_context(node, ctx):
                return prim(engine, node, emit_spec, root_scope)
    return _emit(emit_spec, ctx)


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

    sub_config = config.get("cases", {}).get(value) or config.get("default")
    if sub_config is None:
        return SKIP
    return _run_switch_case(engine, node, sub_config, root_scope)


def _run_switch_case(engine, node, sub_config: dict, root_scope):
    """switch 分支规格：带 `kind` → 原语调度；无 `kind` → 规格本身即 emit。"""
    kind = sub_config.get("kind", "")
    if not kind:
        result = _emit(sub_config, engine._build_context(node))
        if result is not None:
            _bump_switch_stat(engine)
        return result
    prim = get_primitive(kind)
    if prim is None:
        return SKIP
    result = prim(engine, node, sub_config, root_scope)
    if result is not SKIP:
        _bump_switch_stat(engine)
    return result


def _bump_switch_stat(engine) -> None:
    """switch 产出计数（本原语命中一条分支即记一次）。"""
    engine._stats["switch"] = engine._stats.get("switch", 0) + 1


register_primitive("switch", _switch_primitive)
