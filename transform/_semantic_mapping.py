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
from core._protocol import ROW_ORIGIN
from core.define import Node
from analyzer.scope import Scope
from transform.engine import TransformPlugin, AstTransformer, register_plugin


@register_plugin(
    produces=["mapping_tables"],
    shapes={"mapping_tables": {"type": "dict"}},
)
class SemanticMappingPlugin(TransformPlugin):
    """语义映射表构建插件

    由组件 mapping_entries 联合驱动；产出语义映射表（`mapping_tables`，
    契约见 ADR-0015 §3）供 `ConfigDrivenTransform` 消费。
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
        # 行来源（可视化管道，ADR-0015 §2）：{table: {key: [{name, origin}, ...]}}
        self._origins: dict[str, dict[str, list[dict]]] = {}
        self._root_scope: Scope | None = None

    @property
    def tables(self) -> dict[str, Any]:
        """构建后的语义映射表（供 ConfigDrivenTransform 消费）"""
        return dict(self._tables)

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 scope 树，构建映射表"""
        self._tables.clear()
        self._origins.clear()
        self._root_scope = root_scope
        if self._mapping_entries:
            # 从 scope 树构建映射表
            self._build_mappings(root_scope)
        # 物化登记（契约校验，阶段 7）：产出 = 映射表（可能为空表）
        self.note_produced("mapping_tables", self._tables)
        return ast

    def describe(self) -> dict:
        """自述映射表形状 + 行来源（可视化管道，ADR-0015 §2）。

        引擎不解析内容，只收集进单元执行轨迹的 `artifacts` 落盘。
        来源仅覆盖携带 ROW_ORIGIN 的行（展开侧提供溯源时才有）。
        """
        if not self._tables:
            return {}
        out: dict = {}
        for table, content in self._tables.items():
            sources = self._origins.get(table, {})
            out[table] = {
                "rows": _count_rows(content),
                "sources": {k: sources[k] for k in sorted(sources)},
            }
        return out

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
        """对单个符号应用一条 mapping 条目（键 → 源数据 → 注入映射表）。"""
        table = entry.get("table", "")
        if not table:
            return
        if table not in self._tables:
            self._tables[table] = {}

        key = _entry_key(entry, sym, scope)
        source_cfg = entry.get("source", {})
        source_data = _entry_source(source_cfg, sym)

        if not source_cfg.get("items", False):
            return
        # 成品扁平行（resolved_ports）直接注入；否则走字段模板提取
        if _uses_resolved_ports(source_cfg, sym):
            self._inject_flat_rows(table, key, source_data)
            return
        items_result, values = self._process_items(entry, source_data)
        if items_result:
            self._set_nested(self._tables[table], key, items_result)
        if values:
            self._set_nested(
                self._tables[table],
                key,
                values[0] if len(values) == 1 else values,
            )

    def _inject_flat_rows(self, table: str, key: str, source_data: list) -> None:
        """成品扁平行注入（`resolved_ports` 路径）+ 行来源旁路收集。

        行来源（展开侧协议的溯源字段）不进表数据——只旁路收集供
        `describe()` 落盘。
        """
        items_result = []
        origins: list[dict] = []
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
            origin = row.get(ROW_ORIGIN)
            if origin:
                origins.append({"name": entry_row["name"], "origin": origin})
        if items_result:
            self._set_nested(self._tables[table], key, items_result)
            if origins:
                self._origins.setdefault(table, {})[key] = origins

    def _process_items(self, entry: dict, source_data: list) -> tuple[list, list]:
        """处理 items 模式的数据提取（字段模板三形态见 `_apply_field_template`）。"""
        items_result = []
        values = []
        fields = entry.get("fields", {})
        value_key = entry.get("value", "")

        for item in source_data:
            if not isinstance(item, dict):
                continue
            if fields:
                # 逐字段展开"记录集"：每个字段可能把一行变成多行（`[*]` 展开）
                records: list[dict] = [{}]
                for field_name, field_template in fields.items():
                    records = _apply_field_template(
                        records, field_name, str(field_template), item
                    )
                items_result.extend(records)
            # value 简写（单字段表：整表取 item 的一个键）
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


# ── items 模式字段模板（三种形态）────────────────────────────
# 形态由**模板字符串**决定，与语言无关（模板来自组件 mapping_entries）：
#   `{$.key}`  → 取 item 同键的值（源缺键 = 该字段整体跳过）
#   含 `[*]`   → 按路径取值，路径上遇列表按 `[*]` 展开成多行（笛卡尔）
#   其它       → 字面量（每行都写该字符串）
# 回退路径专用：role 端口集有 `resolved_ports` 时 `_apply_entry` 直接注入成品行，
# 不走这里（见 transform/README.md「resolved_ports 优先注入」）。


def _apply_field_template(
    records: list[dict], field_name: str, template: str, item: dict
) -> list[dict]:
    """按模板形态把一列记录展开（返回值可能是新列：`[*]` 形态会增行）。"""
    if template.startswith("{$.") and template.endswith("}"):
        return _records_by_ref(records, field_name, template[3:-1], item)
    if "[*]" in template:
        return _records_by_wildcard(records, field_name, template, item)
    for r in records:
        r[field_name] = template
    return records


def _records_by_ref(
    records: list[dict], field_name: str, field_key: str, item: dict
) -> list[dict]:
    """`{$.key}` 形态：源数据缺该键 → 跳过该字段。

    不把字面模板字符串塞进行数据——emit 端 ref 透传缺失时按"无此属性"处理。
    """
    if field_key not in item:
        return records
    val = item.get(field_key)
    for r in records:
        r[field_name] = val
    return records


def _records_by_wildcard(
    records: list[dict], field_name: str, template: str, item: dict
) -> list[dict]:
    """含 `[*]` 的路径形态：取到列表 → 每个元素与已有行做笛卡尔展开（增行）。

    取到非列表（含空）→ 用模板字符串本身兜底（保持"该字段有值"的语义）。
    """
    val = _walk_wildcard_path(item, template)
    if isinstance(val, list):
        expanded: list[dict] = []
        for single_val in val:
            for r in records:
                nr = dict(r)
                nr[field_name] = single_val
                expanded.append(nr)
        return expanded
    for r in records:
        r[field_name] = val if val else template
    return records


def _walk_wildcard_path(item: dict, template: str) -> Any:
    """`items[*].name` 式路径取值：逐段走（见 `_walk_part`/`_collect_names`）。"""
    val: Any = item
    for part in template.replace("[*]", "").split("."):
        val = _walk_part(val, part.strip())
    return val


def _walk_part(val: Any, part: str) -> Any:
    """路径单段：dict 取键 / list 收该段名 / 其它 → {}（取不到时的哨兵）。"""
    if isinstance(val, dict):
        return val.get(part, {})
    if isinstance(val, list):
        return _collect_names(val, part)
    return {}


def _collect_names(items: list, part: str) -> list[str]:
    """从列表元素收段名：dict 取该键（空值丢弃），字符串元素原样收。"""
    names = []
    for v in items:
        if isinstance(v, dict):
            n = v.get(part, "")
            if n:
                names.append(n)
        elif isinstance(v, str):
            names.append(v)
    return names


def _entry_key(entry: dict, sym: Any, scope: Scope) -> str:
    """键模板 → 映射键（支持 `{scope.name}` 与 `{name}` 两个占位）。"""
    key = entry.get("key", "")
    for k, v in (("scope.name", scope.name), ("name", sym.name)):
        key = key.replace("{" + k + "}", str(v))
    return key


def _uses_resolved_ports(source_cfg: dict, sym: Any) -> bool:
    """源是否走 `resolved_ports` 成品行路径（组件递归展开的完整端口集）。

    role 端口集若已有组件递归展开的结果（含 nested/invert 对侧），它已是扁平
    `{direction, name, packed_range}` 行，直接注入、不走 fields 模板提取。
    引擎只做通用判断（`attr == "ports"` 且有 `resolved_ports`），语言知识在组件侧。
    """
    if source_cfg.get("attr") != "ports":
        return False
    return bool(sym.attrs.get("resolved_ports"))


def _entry_source(source_cfg: dict, sym: Any) -> list:
    """源数据：attr 取值（resolved_ports 优先）→ 列表归一 → 包含过滤 → 排除过滤。"""
    data = sym.attrs.get(source_cfg.get("attr", ""), [])
    if _uses_resolved_ports(source_cfg, sym):
        data = sym.attrs.get("resolved_ports")
    if not isinstance(data, list):
        data = [data] if data else []
    data = _apply_filter(data, source_cfg.get("filter", {}))
    return _apply_exclude_keys(data, source_cfg.get("exclude_keys", []))


def _apply_filter(items: list, filter_cfg: dict) -> list:
    """包含过滤：匹配 `filter` 全部 key=value 的条目才留。"""
    if not filter_cfg:
        return items
    return [
        item
        for item in items
        if isinstance(item, dict)
        and all(item.get(k) == v for k, v in filter_cfg.items())
    ]


def _apply_exclude_keys(items: list, exclude_keys: list) -> list:
    """排除过滤：含 `exclude_keys` 中任一键的条目丢弃（用于过滤 ref 条目）。"""
    if not exclude_keys:
        return items
    return [
        item
        for item in items
        if not (isinstance(item, dict) and any(k in item for k in exclude_keys))
    ]


def _count_rows(node: Any) -> int:
    """统计映射表嵌套结构中的行数（表叶子列表的元素总数）。"""
    if isinstance(node, list):
        return sum(len(x) if isinstance(x, list) else 1 for x in node)
    if isinstance(node, dict):
        return sum(_count_rows(v) for v in node.values())
    return 0

