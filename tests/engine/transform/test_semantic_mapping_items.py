"""items 模式字段模板三形态（`SemanticMappingPlugin._process_items`）。

这是 role 端口映射的**回退路径**：符号带 `resolved_ports` 时 `_apply_entry` 直接
注入成品行（`transform/README.md`「resolved_ports 优先注入」），不带时才走
`_process_items` 的模板提取——该回退路径此前没有直接覆盖，改它没有探针。

三形态由**模板字符串**决定（模板来自组件 `mapping_entries`，语言无关）：

| 模板 | 语义 |
|------|------|
| `{$.key}` | 取 item 同键的值；源缺键 → **该字段整体跳过**（不塞字面模板串） |
| 含 `[*]` | 路径取值，路上遇列表按段名展开成多行（与已有行做笛卡尔展开） |
| 其它 | 字面量（每行都写该字符串） |

Doc: transform/README.md（语义映射机制）、grammar/verilog/plugins/typed_ports/_mapping.py
"""

from transform._semantic_mapping import SemanticMappingPlugin


def _plugin() -> SemanticMappingPlugin:
    return SemanticMappingPlugin({})


def test_ref_form_reads_same_key():
    """`{$.key}`：取 item 同键值。"""
    entry = {"fields": {"direction": "{$.direction}"}}
    items, values = _plugin()._process_items(
        entry, [{"direction": "input"}, {"direction": "output"}]
    )
    assert items == [{"direction": "input"}, {"direction": "output"}]
    assert values == []


def test_ref_form_missing_key_skips_field():
    """源数据缺键 → 跳过该字段（不把字面模板字符串塞进行数据）。"""
    entry = {"fields": {"direction": "{$.direction}", "name": "{$.name}"}}
    items, _ = _plugin()._process_items(
        entry, [{"direction": "input", "name": "a"}, {"direction": "output"}]
    )
    assert items == [{"direction": "input", "name": "a"}, {"direction": "output"}]


def test_wildcard_form_expands_list_into_rows():
    """`[*]`：取到列表 → 每个元素与已有行笛卡尔展开（一行变多行）。"""
    entry = {"fields": {"direction": "{$.direction}", "name": "items.items[*].name"}}
    src = [{"direction": "input", "items": {"items": [{"name": "a"}, {"name": "b"}]}}]
    items, _ = _plugin()._process_items(entry, src)
    assert items == [
        {"direction": "input", "name": "a"},
        {"direction": "input", "name": "b"},
    ]


def test_wildcard_form_empty_list_drops_row():
    """`[*]` 展开为空 → 该行整体消失（零行，不是"留个空字段"）。"""
    entry = {"fields": {"name": "items.items[*].name"}}
    items, _ = _plugin()._process_items(entry, [{"items": {"items": []}}])
    assert items == []


def test_wildcard_form_missing_path_falls_back_to_template():
    """`[*]` 路径取不到（{} / 非列表）→ 用模板字符串本身兜底（锁定既有语义）。"""
    entry = {"fields": {"w": "a[*].b"}}
    items, _ = _plugin()._process_items(entry, [{"other": 1}])
    assert items == [{"w": "a[*].b"}]


def test_literal_form_writes_same_string_per_row():
    """字面量形态：每行都写该字符串。"""
    entry = {"fields": {"kind": "role"}}
    items, _ = _plugin()._process_items(entry, [{"x": 1}, {"x": 2}])
    assert items == [{"kind": "role"}, {"kind": "role"}]


def test_value_shorthand_skips_non_dict_items():
    """value 简写：取 item 的一个键；非 dict 项整体跳过（fields 与 value 共享这一判定）。"""
    entry = {"value": "name"}
    items, values = _plugin()._process_items(
        entry, [{"name": "a"}, "not-a-dict", {"name": "b"}]
    )
    assert items == []
    assert values == ["a", "b"]
