# Gap — renderer 注释回插保真（锚点启发式，±3 行窗口）

- 状态：接受（real 保真度门禁锁定现状；attachment 是前进方向）
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）；`renderer/renderer_architecture.md`「功能缺口」B3/缺口 2
- 参照：prettier/verible 的注释槽位模型

## 缺口是什么

注释回插是 **best-effort**：注释经锚点映射回插。保留路径精确；展开路径
（宏展开、transform）锚点可能漂移——注释可能被丢弃而非冒险破坏结构，是刻意
取舍。机制细节（世界 A）：锚点路径 `inline_comment.py` 在列表结构内被
production skip 吞掉的注释，渲染后按锚点窗口（±3 行启发式）回插；attachment
路径（阶段 4 注释遍）把行尾注释挂节点（Doc 一等公民）但未完全覆盖块结束符
注释——与锚点回插双轨并存（restore 去重防重复）。

## 为什么是缺口（影响面）

注释密集源码（条件编译块、宏展开后、transform 后）可能错位/丢弃——攻击面
在 real 保真度门禁（8 module + 关键构造）可测范围内；跨文件/宏复杂场景是
残余风险。对"格式化后注释不乱跑"的用户预期影响最大。

## 成熟解法参照（见贤思齐）

- attachment 路径（LineSuffix Doc 一等公民）是成熟方向（prettier 注释槽位
  模型）；锚点回插是它的过渡兜底。
- 块结束符注释（`end`/`endmodule` 后）是 attachment 未覆盖的最后一类——补全
  后锚点回插可退居纯兜底。

## 可实现性

- 补 attachment 覆盖块结束符注释 → 锚点回插仅剩 only_tpc marker 通道。
- 验证：`tests/engine/parser/test_comment_attachment.py` + real 保真度门禁 +
  e2e 注释样例（`tests/e2e/samples/normal/ref/ref_comments.v` 类）。
- 当前：接受现状（见 renderer_architecture 缺口 2，接受理由完整）。

## 关联条目

- `renderer/renderer_architecture.md`（世界 A：注释处理双轨 + 缺口 B3/2）
- 原 `docs/known_limitations.md`（Correctness：comment restoration best-effort）
- attachment 测试：`tests/engine/parser/test_comment_attachment.py`
