"""
SemanticMappingPlugin — 语义映射表构建 + 后处理管线

职责：
    作为 transform 管线的第一个插件，在 ConfigDrivenTransform 之前执行。
    遍历 scope 树，从符号 attrs 构建语义映射表（type_ports_flat, type_revert 等），
    并对映射表执行后处理（如 revert 方向反转）。

设计原理：
    所有语言专用的"语义对齐逻辑"由 TOML 配置驱动，Python 只提供通用原语。
    - mapping.* 条目：定义"如何从符号构建映射表"
    - resolve.* 条目：定义"如何后处理映射表"（使用 value_map 等通用原语）

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
        kind = "value_map"             ← 后处理原语类型
        source_table = "type_revert"   ← 源映射表
        target_table = "type_ports_flat" ← 目标映射表
        field = "direction"            ← 要变换的字段
        map = { input = "output", ... } ← 值映射表（语言专用）

管线顺序：
    1. SemanticMappingPlugin._build_mappings() — 从 scope 树构建原始映射表
    2. SemanticMappingPlugin._run_resolve()     — 执行所有 resolve.* 后处理
    3. ConfigDrivenTransform.process()          — 使用映射表展开类型端口
"""

from typing import Any, Optional
from core.define import Node
from analyzer.scope import Scope
from transform.post.ast_transformer import TransformPlugin
from transform.post.engine.primitives import value_map


class SemanticMappingPlugin(TransformPlugin):
    """语义映射表构建 + 后处理管线插件

    由 _analyzer.toml 的 [mapping.*] 和 [resolve.*] 联合驱动。
    """

    def __init__(self, raw_config: Optional[dict] = None):
        """初始化

        Args:
            raw_config: _analyzer.toml 的原始 dict 内容（含 mapping.* 和 resolve.* 等）
        """
        raw = raw_config or {}
        # mapping 条目：从符号构建映射表
        self._mapping_entries: list[dict] = [
            v for v in raw.values()
            if isinstance(v, dict) and "trigger" in v
        ]
        # resolve 条目：映射表后处理
        self._resolve_entries: list[dict] = [
            v for v in raw.values()
            if isinstance(v, dict) and v.get("kind") in ("value_map",)
        ]
        self._tables: dict[str, Any] = {}

    @property
    def tables(self) -> dict[str, Any]:
        """构建后的语义映射表（供 ConfigDrivenTransform 消费）"""
        return dict(self._tables)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 scope 树，构建映射表 + 执行后处理管线"""
        self._tables.clear()
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
            items_result, values = self._process_items(entry, source_data)
            if items_result:
                self._set_nested(self._tables[table], key, items_result)
            if values:
                self._set_nested(
                    self._tables[table], key,
                    values[0] if len(values) == 1 else values,
                )

    def _process_items(
        self, entry: dict, source_data: list
    ) -> tuple[list, list]:
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
            kind = "value_map" — 用值映射表变换指定字段
        """
        for entry in self._resolve_entries:
            kind = entry.get("kind", "")
            if kind == "value_map":
                self._apply_value_map(entry)

    def _apply_value_map(self, entry: dict) -> None:
        """通用 value_map 后处理：查表替换指定字段的值

        配置格式:
            kind = "value_map"
            source_table = "type_revert"       # 源表：包含 revert 引用关系的表
            target_table = "type_ports_flat"   # 目标表：包含要变换数据的表
            source_to_target_key = [           # 如何从 source 表key映射到 target 表key
                "{type_name}.{target_role}",   # target 表 key 模板
            ]
            source_key_parts = ["{type_name}", "{role_name}"]  # source 表 key 的组成部分
            target_role_value = "${target_role}"               # source 表 value 字段
            field = "direction"                # 要变换的字段名
            map = { input = "output", ... }    # 值映射表（语言专用）
        """
        source_table_key = entry.get("source_table", "")
        target_table_key = entry.get("target_table", "")
        field = entry.get("field", "")
        value_map_cfg = entry.get("map", {})

        source_table = self._tables.get(source_table_key, {})
        target_table = self._tables.get(target_table_key, {})

        if not source_table or not target_table or not value_map_cfg:
            return

        from copy import deepcopy

        for type_name, roles in source_table.items():
            for role_name, target_role_val in roles.items():
                # target_role_val 是 source 表中存储的值（如 "master"）
                if not isinstance(target_role_val, str):
                    continue

                # 在 target 表中查找目标角色的数据
                target_data = target_table.get(type_name, {}).get(target_role_val)
                if not target_data:
                    continue

                # 复制并做 value_map 变换
                resolved = []
                for item in target_data:
                    if not isinstance(item, dict):
                        continue
                    new_item = deepcopy(item)
                    if field in new_item:
                        new_item[field] = value_map(
                            new_item[field], value_map_cfg
                        )
                    resolved.append(new_item)

                # 写回 target 表
                target_table.setdefault(type_name, {})[role_name] = resolved
