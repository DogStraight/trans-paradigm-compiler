# Gap — renderer 注释回插保真（锚点启发式，±3 行窗口）

- 状态：**立项中**（TODO「缺口闭环队列」④，2026-09-12 排队）：已部分闭环
  （2026-09-12："模块体首注释漂到 module 声明前"已修，提交 `5ad5bb4` +
  回归 `tests/languages/verilog/test_comment_body_head.py`）；在队项 =
  attachment 覆盖块结束符注释
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）；`renderer/renderer_architecture.md`「功能缺口」B3/缺口 2
- 参照：prettier/verible 的注释槽位模型

## 缺口是什么

> **2026-09-12 更新**：本档记录的"模块体首注释漂到 module 声明前"具体缺陷
> **已修**（提交 `5ad5bb4`，`join.py` 拆段加"只拆非分段节点"判据）——复现、
> 定位与修法见下「最小复现与触发条件」节。缺口剩余部分 = attachment 覆盖
> 块结束符注释（前进方向），以及展开路径的其余锚点漂移风险。

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

## 最小复现与触发条件（2026-09-12，0.1.2 阶段 9 定位收敛）

**最小复现**（12 行，与宏/typed_ports 无关）：

```verilog
module m(
    input clk,
    output reg [7:0] d
);
    // 注释 A
    // 注释 B
    sub_mod u_sub ( .clk(clk), .d(d) );

    always @(posedge clk) begin
        d <= d + 1;
    end
endmodule
```

渲染结果把两条注释放到了 `module m(...)` **声明之前**（顶格）。

**触发条件**（变体实测）：模块体**第一个元素是注释** → 漂到 module 前；
注释在任一成员**之后**（如同在 assign 后）→ 位置正确。

**定位范围**：

- parser 侧**正确**：`ModuleDecl.sub_node` 首位挂 Comment 子节点
  （`_claim_head_comments`，ADR-0013 B1.3 模型）；
- **渲染入参结构与对照场景同构**（`[Comment, Comment, X, AlwaysStmt]`），但
  `X = ModuleInst` 时渲染到 module 前、`X = ImplBindingWithInterface` 时正确
  → 问题在**渲染层的 head/body 分段**（`ModuleDecl.renderer.{head,body,tail}`，
  body `role = "flatten"`），与 parser/transform 无关；
- 与 formatter 无关（`format_output=False` 同样漂移）；
- 既有性：改造前提交 `55123f4`（typed_ports 桥插件时代）行为相同。
- 影响量化：`ref_spi_inf` 展开路径含注释口径字符相似度 ≈ 0.73（代码结构 1:1），
  `run_all_tests.py` 的 `_strip_all` 口径仍过阈值（X:OK）→ 门禁不报。

**修法（已实施 2026-09-12）**：`renderer/primitives/join.py` 的"容器首部
Comment 拆段"（ADR-0013 B1.3）加判据——**只拆非分段节点**（列表项，无
head/body/tail）；分段节点（`ModuleDecl` 等）的 body 首注释归
`render_node` 的 body 段渲染（head 之后）。效果：最小复现正确、
`ref_spi_inf` 展开路径注释回到 ref 位置（第 11 行）；回归
`tests/languages/verilog/test_comment_body_head.py`。
· 附带修正：旧实现对分段节点执行 `subs.pop(0)` 就地改 AST（渲染不该改树），
加判据后不再触发。

## 关联条目

- `renderer/renderer_architecture.md`（世界 A：注释处理双轨 + 缺口 B3/2）
- 原 `docs/known_limitations.md`（Correctness：comment restoration best-effort）
- attachment 测试：`tests/engine/parser/test_comment_attachment.py`
