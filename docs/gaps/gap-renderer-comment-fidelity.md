# Gap — renderer 注释回插保真（锚点启发式，±3 行窗口）

- 状态：接受（best-effort：保留路径精确，展开路径残余漂移风险）
- 关联：`renderer/renderer_architecture.md`（注释处理双轨 + 缺口 B3/2）
- 参照：prettier/verible 的注释槽位模型

## 边界是什么

注释回插是 **best-effort**：保留路径精确（注释挂 AST 槽位，见
`renderer/renderer_architecture.md` 注释处理节）；展开路径（宏展开、transform）
锚点可能漂移——注释可能被丢弃而非冒险破坏结构，是刻意取舍。
双轨：attachment（行尾/块边界 trailing 等挂节点，模块头注释经
`_insert_before_trailing_break` 落位）+ 锚点回插兜底（`inline_comment.py`：被
production skip 吞掉的结构内注释按锚点窗口 ±3 行启发式回插；restore 去重防重复）。

## 为什么是边界（影响面）

注释密集源码（条件编译块、宏展开后、transform 后）可能错位/丢弃——攻击面
在 real 保真度门禁（8 module + 关键构造）可测范围内；跨文件/宏复杂场景是
残余风险。对"格式化后注释不乱跑"的用户预期影响最大。

## 成熟解法参照（见贤思齐）

- attachment 路径（LineSuffix Doc 一等公民）是成熟方向（prettier 注释槽位
  模型）；锚点回插是它的过渡兜底。
- 块结束符注释（`end`/`endmodule` 后）是 attachment 未覆盖的最后一类——补全
  后锚点回插可退居纯兜底。

## 可实现性

- 继续补 attachment 覆盖（变换路径注释迁移）→ 锚点回插退居纯兜底。
- 验证：`tests/engine/parser/test_comment_attachment.py` + real 保真度门禁 +
  e2e 注释样例（`tests/e2e/samples/normal/ref/ref_comments.v` 类）。
- 当前：接受现状（见 renderer_architecture 缺口 2，接受理由完整）。

## 关联条目

- `renderer/renderer_architecture.md`（世界 A：注释处理双轨 + 缺口 B3/2）
- 门禁：`tests/engine/parser/test_comment_attachment.py`（含逐行位置敏感用例）
  + `tests/languages/verilog/test_comment_body_head.py` + real 保真度门禁
