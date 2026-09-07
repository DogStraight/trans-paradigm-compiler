"""
SemanticMappingPlugin — 语义映射表构建 + 后处理管线

职责：
    作为 transform 管线的第一个插件，在 ConfigDrivenTransform 之前执行。
    遍历 scope 树，从符号 attrs 构建语义映射表（type_ports_flat, type_invert 等），
    并对映射表执行后处理（如 invert 方向反转）。

设计原理：
    所有语言专用的"语义对齐逻辑"由 TOML 配置驱动，Python 只提供通用原语。
    - mapping.* 条目：定义"如何从符号构建映射表"
    - resolve.* 条目：定义"如何后处理映射表"（使用 apply_refs 原语）

配置：
    由 _analyzer.toml 的 [mapping.*] 和 [resolve.*] 条目驱动。

    mapping 条目：
        trigger = { kind = "..." }    ← 符号类别触发
        table = "name"                ← 输出到 mapping["name"]
        key = "{scope.name}.{name}"   ← 键模板
        source = { attr = "ports", ... } ← 从符号 attrs 提取
        items = true                   ← 源数据是列表，逐项处理
        fields = { ... }               ← 每项提取的子字段

    resolve 条目（后处理管线）：
        kind = "apply_refs"            ← 消费 _ref_callbacks，展开并合并到表中

管线顺序：
    1. SemanticMappingPlugin._build_mappings() — 从 scope 树构建原始映射表
    2. SemanticMappingPlugin._run_resolve()     — 执行所有 resolve.* 后处理
    3. ConfigDrivenTransform.process()          — 使用映射表展开类型端口
Doc: docs/language_walkthrough.md（语义映射）
"""

from typing import Any
from core.define import Node
from analyzer.scope import Scope
from transform.engine import TransformPlugin, AstTransformer, register_plugin


@register_plugin
class SemanticMappingPlugin(TransformPlugin):
    """语义映射表构建 + 后处理管线插件

    由 _analyzer.toml 的 [mapping.*] 和 [resolve.*] 联合驱动。
    """

    def __init__(self, raw_config: dict | None = None):
        """初始化语义映射插件。

        Args:
            raw_config: 映射配置；缺省取共享上下文 mapping_cfg（_analyzer.toml
                的原始内容，含 mapping.* 和 resolve.*）。
        """
        if raw_config is None:
            raw_config = AstTransformer._shared_ctx.get("mapping_cfg", {})
        raw = raw_config or {}
        # mapping 条目：从符号构建映射表
        self._mapping_entries: list[dict] = [
            v for v in raw.values() if isinstance(v, dict) and "trigger" in v
        ]
        # resolve 条目：映射表后处理
        self._resolve_entries: list[dict] = [
            v
            for v in raw.values()
            if isinstance(v, dict) and v.get("kind") == "apply_refs"
        ]
        self._tables: dict[str, Any] = {}
        self._root_scope: Scope | None = None

    @property
    def tables(self) -> dict[str, Any]:
        """构建后的语义映射表（供 ConfigDrivenTransform 消费）"""
        return dict(self._tables)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 scope 树，构建映射表 + 执行后处理管线"""
        self._tables.clear()
        self._root_scope = root_scope
        if not self._mapping_entries:
            return ast

        # 1. 从 scope 树构建映射表
        self._build_mappings(root_scope)

        # 2. 执行后处理管线
        self._run_resolve()

        return ast

    # ── 映射表构建 ──

    def _build_mappings(self, scope: Scope) -> None:
        """递归遍历 scope 树，为匹配的符号构建映射表条目"""
        for sym in scope.symbols.values():
            for entry in self._mapping_entries:
                trigger = entry.get("trigger", {})
                if trigger.get("kind") != sym.kind:
                    continue
                self._apply_entry(entry, sym, scope)

        # 递归子域
        for child in scope.children:
            self._build_mappings(child)

    def _apply_entry(self, entry: dict, sym: Any, scope: Scope) -> None:
        """对单个符号应用一条 mapping 条目"""
        table = entry.get("table", "")
        if not table:
            return
        if table not in self._tables:
            self._tables[table] = {}

        # 构建映射键
        key_template = entry.get("key", "")
        ctx = {"scope.name": scope.name, "name": sym.name}
        key = key_template
        for k, v in ctx.items():
            key = key.replace("{" + k + "}", str(v))

        # 提取源数据
        source_cfg = entry.get("source", {})
        source_data = sym.attrs.get(source_cfg.get("attr", ""), [])
        # resolved_ports 优先：role 端口集若已有组件递归展开的完整结果
        # （sym.attrs["resolved_ports"]，含 nested/invert 对侧展开），直接用——
        # 它已是扁平 {direction, name, packed_range} 行，fields 提取兼容。
        # raw ports（声明捕获，含 nested/invert 标记）是回退。引擎只做通用
        # 判断（attr=="ports" 且有 resolved_ports），语言知识在组件侧。
        if (
            source_cfg.get("attr") == "ports"
            and sym.attrs.get("resolved_ports")
        ):
            source_data = sym.attrs.get("resolved_ports")
        if not isinstance(source_data, list):
            source_data = [source_data] if source_data else []

        # 筛选（包含：匹配 filter 中所有 key=value 的条目）
        filter_cfg = source_cfg.get("filter", {})
        if filter_cfg:
            filtered = []
            for item in source_data:
                if isinstance(item, dict) and all(
                    item.get(k) == v for k, v in filter_cfg.items()
                ):
                    filtered.append(item)
            source_data = filtered

        # 排除（含 exclude_keys 中任一 key 的条目被跳过，用于过滤 ref 条目）
        exclude_keys = source_cfg.get("exclude_keys", [])
        if exclude_keys:
            source_data = [
                item
                for item in source_data
                if not (isinstance(item, dict) and any(k in item for k in exclude_keys))
            ]

        # 按 items 逐项处理
        if source_cfg.get("items", False):
            # resolved_ports 优先路径：源数据已是成品扁平行
            # {direction, name, packed_range?}（组件递归展开的完整端口集，
            # 含 nested/invert 对侧展开），直接透传注入映射表，不走字段
            # 模板提取（那套 items.items[*].name 是给 raw 声明结构用的）。
            if source_cfg.get("attr") == "ports" and sym.attrs.get("resolved_ports"):
                items_result = []
                for row in source_data:
                    if not isinstance(row, dict) or not row.get("name"):
                        continue
                    entry_row: dict = {
                        "direction": row.get("direction", ""),
                        "name": row.get("name", ""),
                    }
                    if row.get("packed_range") is not None:
                        entry_row["packed_range"] = row["packed_range"]
                    items_result.append(entry_row)
                if items_result:
                    self._set_nested(self._tables[table], key, items_result)
            else:
                items_result, values = self._process_items(entry, source_data)
                if items_result:
                    self._set_nested(self._tables[table], key, items_result)
                if values:
                    self._set_nested(
                        self._tables[table],
                        key,
                        values[0] if len(values) == 1 else values,
                    )

    def _process_items(self, entry: dict, source_data: list) -> tuple[list, list]:
        """处理 items 模式的数据提取"""
        items_result = []
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
                        # 源数据缺该键 → 跳过该字段（不把字面模板字符串
                        # 塞进行数据，emit 端 ref 透传缺失时按"无此属性"处理）
                        if field_key not in item:
                            continue
                        val = item.get(field_key)
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
                items_result.extend(records)

            # value 简写
            value_key = entry.get("value", "")
            if value_key:
                values.append(item.get(value_key, ""))

        return items_result, values

    @staticmethod
    def _set_nested(d: dict, key: str, value: Any) -> None:
        """将 "spi.master" 展开为 {spi: {master: value}} 存入 dict"""
        parts = key.split(".")
        parent = d
        for p in parts[:-1]:
            parent = parent.setdefault(p, {})
        parent[parts[-1]] = value

    # ── 后处理管线 ──

    def _run_resolve(self) -> None:
        """执行所有 resolve.* 后处理条目

        目前支持:
            kind = "apply_refs" — 消费分析器产出的 _ref_callbacks，展开 ref 并合并
        """
        for entry in self._resolve_entries:
            kind = entry.get("kind", "")
            if kind == "apply_refs":
                self._apply_refs()

    # ── 变换回调消费：apply_refs ──

    def _apply_refs(self) -> None:
        """消费分析器产出的 _ref_callbacks，展开 ref 并合并到 type_ports_flat

        协议（分析器→变换器）：
            输入: sym.attrs["_ref_callbacks"]
                [{
                    "kind": "nested",           # 引用类型
                    "resolved_ports": [...],      # scope 知识（分析器已查好的端口数据）
                    "prefix": "upstream",        # nested: 实例名前缀
                    "source_type": "axis",       # nested: 源类型名
                    "source_role": "master",     # 源角色名
                }]

        本步骤只做机械操作（不涉及 scope 查找）：
            - nested:  deepcopy + prefix 端口名
            - invert:  deepcopy + invert_map 反转 direction

        输出: type_ports_flat 表中追加展开后的扁平端口 { direction, name }
        """
        target = self._tables.get("type_ports_flat")
        if target is None:
            return
        root = getattr(self, "_root_scope", None)
        if root is None:
            return


        self._walk_refs(root, target)

    def _walk_refs(
        self, scope: Scope, target: dict
    ) -> None:
        """递归遍历 scope 树，消费 _ref_callbacks

        输入（来自分析器 resolve_refs 原语）：
            sym.attrs["_ref_callbacks"] = [
                {
                    "kind": "nested",           # 跨类型引用
                    "resolved_ports": [           # scope 查找结果（嵌套结构）
                        {
                            "direction": "input",
                            "items": { "items": [{ "name": "tvalid" }, ...] }
                        },
                        ...
                    ],
                    "prefix": "upstream",        # nested: 实例名前缀
                    "source_type": "axis",       # nested: 源类型名
                    "source_role": "master",
                },
                {
                    "kind": "invert",            # 同类型反转引用
                    "resolved_ports": [...],
                    "source_role": "master",
                }
            ]

        处理（仅机械操作，无 scope 查找）：
            1. _flatten_port 将嵌套 {direction, items: {items: [{name}]}}
            展开为扁平 {direction, name}
            2. nested: _prefix_port_name 给 name 加前缀
            3. _merge_to_flat 合并到 type_ports_flat

        输出：
            type_ports_flat["{scope.name}.{sym.name}"] 追加扁平端口条目
            [{ "direction": "output", "name": "upstream_tvalid" }, ...]

        下游消费：
            ConfigDrivenTransform expand 原语
            → lookup type_ports_flat → foreach → switch → emit AST 节点

        注意：invert 方向反转已在分析器阶段由 attach_invert_map 原语完成，
        变换器不再感知 direction/invert_map——只合并已处理好的端口数据。
        """
        for sym in scope.symbols.values():
            # role 若有组件递归展开的 resolved_ports（含 nested/invert 对侧，
            # 已在 _apply_entry 完整注入 type_ports_flat）→ 跳过本处 _ref_callbacks
            # merge，避免 analyze 固化的旧/坏回调数据重复叠加（P1.5 invert L2/L3
            # 修复后 analyze 侧 _ref_callbacks 不再作展开权威）。
            if (
                getattr(sym, "kind", "") == "role"
                and sym.attrs.get("resolved_ports")
            ):
                continue
            callbacks = sym.attrs.get("_ref_callbacks", [])
            if not isinstance(callbacks, list):
                continue
            # 构造 key：{scope.name}.{sym.name}
            key = f"{scope.name}.{sym.name}"

            for cb in callbacks:
                resolved_ports = cb.get("resolved_ports", [])
                if not resolved_ports:
                    continue

                # resolved_ports 已在分析器阶段拍平为 {direction, name} 格式
                prefix = cb.get("prefix", "")
                expanded = []
                for p in resolved_ports:
                    if prefix and isinstance(p, dict):
                        p["name"] = f"{prefix}_{p['name']}" if p.get("name") else p.get("name", "")
                    expanded.append(p)
                self._merge_to_flat(target, key, expanded)

        for child in scope.children:
            self._walk_refs(child, target)

    @staticmethod
    def _merge_to_flat(target: dict, key: str, ports: list[dict]) -> None:

        parts = key.split(".")
        parent = target
        for p in parts[:-1]:
            parent = parent.setdefault(p, {})
        existing = parent.get(parts[-1], [])
        if not isinstance(existing, list):
            existing = [existing]
        # 过滤无效行：无端口名的行（如嵌套引用 dict 拍平残留的空行）不应进入
        # 映射表——expand 端 switch 对空 direction 无匹配分支会返回 SKIP 并
        # 泄漏进 AST（渲染成字面 "SKIP"）。此处是根因防御（任何来源的空行）。
        existing.extend(p for p in ports if not (isinstance(p, dict) and not p.get("name")))
        parent[parts[-1]] = existing


# ── 模块级辅助函数（不依赖类上下文）────────────


def _prefix_port_name(port: dict, prefix: str) -> None:
    """为端口 name 添加前缀"""
    if "name" in port and isinstance(port["name"], str):
        port["name"] = f"{prefix}_{port['name']}"
    if "items" in port and isinstance(port["items"], dict):
        inner = port["items"].get("items", [])
        if isinstance(inner, list):
            for item in inner:
                _prefix_port_name(item, prefix)

