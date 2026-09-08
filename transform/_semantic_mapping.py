"""
SemanticMappingPlugin — 语义映射表构建 + 后处理管线

职责：
    作为 transform 管线的第一个插件，在 ConfigDrivenTransform 之前执行。
    遍历 scope 树，从符号 attrs 构建语义映射表（type_ports_flat, type_invert 等），
    并对映射表执行后处理（如 invert 方向反转）。

设计原理：
    所有语言专用的"语义对齐逻辑"由 TOML 配置驱动，Python 只提供通用原语。
    mapping 条目定义"如何从符号构建映射表"。

配置：
    由组件 .py 暴露的 mapping_entries 驱动（组件级 tpc.toml [analyzer].handlers
    收集，见 core/component_protocol.md）。

    mapping 条目：
        trigger = { kind = "..." }    ← 符号类别触发
        table = "name"                ← 输出到 mapping["name"]
        key = "{scope.name}.{name}"   ← 键模板
        source = { attr = "ports", ... } ← 从符号 attrs 提取
        items = true                   ← 源数据是列表，逐项处理
        fields = { ... }               ← 每项提取的子字段

管线顺序：
    1. SemanticMappingPlugin._build_mappings() — 从 scope 树构建映射表
    2. ConfigDrivenTransform.process()         — 使用映射表展开类型端口
    （resolve.*/apply_refs 后处理已删——role 端口展开由组件 postpass 写
    resolved_ports、_apply_entry 直接注入，见 ADR-0015 关联的 typed_ports
    step 2；引擎 resolve_refs 原语链已整体移除）
Doc: docs/language_walkthrough.md（语义映射）
"""

from typing import Any
from core.define import Node
from analyzer.scope import Scope
from transform.engine import TransformPlugin, AstTransformer, register_plugin


@register_plugin
class SemanticMappingPlugin(TransformPlugin):
    """语义映射表构建插件

    由组件 mapping_entries 联合驱动。
    """

    def __init__(self, raw_config: dict | None = None):
        """初始化语义映射插件。

        Args:
            raw_config: 映射配置；缺省取共享上下文 mapping_cfg（组件
                mapping_entries 的原始内容）。
        """
        if raw_config is None:
            raw_config = AstTransformer._shared_ctx.get("mapping_cfg", {})
        raw = raw_config or {}
        # mapping 条目：从符号构建映射表
        self._mapping_entries: list[dict] = [
            v for v in raw.values() if isinstance(v, dict) and "trigger" in v
        ]
        self._tables: dict[str, Any] = {}
        self._root_scope: Scope | None = None

    @property
    def tables(self) -> dict[str, Any]:
        """构建后的语义映射表（供 ConfigDrivenTransform 消费）"""
        return dict(self._tables)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 scope 树，构建映射表"""
        self._tables.clear()
        self._root_scope = root_scope
        if not self._mapping_entries:
            return ast

        # 从 scope 树构建映射表
        self._build_mappings(root_scope)

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

