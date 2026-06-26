# 管线调试—已知问题速查

以下问题在 pipeline-debug 调试过程中已被发现并修复，供快速对照参考。

| 现象 | 根因 | 修复 |
|------|------|------|
| `所有候选规则匹配失败: 'end'` | ModuleBlock/ProcBlock 的 block_end 为空字符串，block body 无法识别结束符，只能靠 parse_sentence 返回 None 退出 | `00_blocks.toml` 中的 block_end 未设置 |
| `所有候选规则匹配失败: '<='` | 非阻塞赋值 `<=' 被 PortTail 等非语句规则优先匹配，因为 `statement_rule_names` 过滤条件用了 `is not None`（`end_case` 默认值是 `[]` 而非 `None`） | `run_pipeline.py` 和 `main_parser.py` 改为 `getattr(rule, "end_case", [])` |
| PortTail 在模块体内被误匹配 | 同上——PortTail 无 end_case 但因过滤条件错误被加入候选列表 | 同上 |
| 注释与 module 声明合并到同一行 | `Root.layout = { join = "\\n" }` 中 `"\\n".rstrip()` 返回 `""`，`SoftLine` 在 group flat 模式被展平为空格 | `join_prim.py`：分隔符为 `\\n` 时使用 `Break` 硬换行且不 group |
| `array2d_test( )` 多余空格 | 端口组 `{ soft = true }` 在无端口时产生 `( )` | `01_module.toml`：端口组添加 `ref = "ports"` + `{ break = true }` |
| 模块端口 `)` 不在独立行 | 同上——软换行被 group flat 模式吞掉 | 同上 |
| `);` 后无空白行 | ModuleDecl head 尾部缺少换行 | `01_module.toml`：head 末尾添加 `{ break = true }` |
| `.port_b` 比 `.port_a` 多 8 空格 | `NamedPortList` 的 `nest = 2` 与父级 body indent 叠加 | `04_statements.toml`：移除 `nest = 2` |
| 生成代码完全为空（仅头部） | parser 返回 Root 仅 1 节点，整个文件未解析 | 检查 Token 流 + 候选规则 |
| `module array2d_test( )` 多余空格 | `{ soft = true }` 在无端口时 flat 模式产生 `( )` | `01_module.toml`：端口组加 `ref = "ports"` 条件判断 |

> 此文件维护于 pipeline-debug skill 的迭代过程中。新增发现请同步更新。
