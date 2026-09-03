# ADR-0013: 注释单机制（AST 元信息唯一挂载，消除锚点回插双轨）

- Status: draft（未立项；立项实现后升 accepted）
- Date: 2026-09-04
- Supersedes: 注释双轨机制（`_comment_anchors`/`_line_comment_anchors` 渲染后
  字符串级回插作为普通注释通道）；references.md「pratt 前缀吞注释」边界

## 背景

注释恢复机制长期双轨并存，复杂度高且能力不对称：

- **结构序轨**（频域）：`_comment_slots` 元信息挂 AST 节点（trailing /
  inline_after）+ block 层 Comment 一等节点（`collect_line_comments`），
  renderer 按槽位渲染。
- **时域兜底轨**：`_comment_anchors` / `_line_comment_anchors`（parser
  旁路列表）→ 渲染后 `restore_comments` / `restore_line_comments`
  按 ±3 行窗口字符串级回插。

e2e 注释样本逐注释实测（2026-09-04，ref_comments.v / ref_inline_test.v）：
同一文件内相邻注释走 5 种不同机制（Comment 节点 / trailing 槽 /
inline_after 槽 / _attached_comments+anchors / 纯 anchors midline），
`_attached_comments`、`_comment_anchors`、`inline_after` 之间还要靠
"渲染端删槽 + restore 去重"防双份。

**核心缺口**：pratt 解析器输出不带注释元信息。`a + /* c */ b` 的注释位于
operator 间隙（`+` 与 `b` 之间），pratt 前缀位直接跳过并经 `comment_sink`
丢进 `parser._comment_anchors`（midline）——**全管线唯一"只存在于 parser
旁路列表、不在 AST 里"的注释类**。atom 位（`x /* c */ + y`）因走
parse_token → collect_following_comments 反而能进槽位，operator 位不能，
对称位置机制分裂。

## 决策

消除双轨：**源注释只有一种机制——挂 AST 节点元信息 + 节点内位置标签**，
parser 唯一生产、renderer 唯一消费，普通注释不再走渲染后字符串级回插。
tpc marker（`/*<tpc:macro:N>*/` 等预处理器占位）是跨阶段产物，生命周期
不同，维持独立通道（见"范围边界"）。

### 1. 唯一数据面：注释 = 节点元信息 + 节点内 gap 标签

每条源注释挂在某个 AST 节点的元信息属性上（沿用 `_comment_slots`
下划线属性族，normalizer 保留、dump 过滤），携带**节点内位置标签**而非
token 文本锚：

- `before_first` — 节点首元素前（行首独立注释并入下一条语句 leading
  槽位语义，见决策 4）
- `between_element_i_and_i+1` — 节点内第 i 与第 i+1 个元素之间
- `after_element_i` — 节点第 i 个元素后（行尾/行中）

不再按 token 文本键控（消灭"锚文本重复歧义/锚不在布局里就落回时域"）。
`//` 行注释的"必须断行"语义由注释文本自身携带，renderer 消费时执行。

### 2. 唯一生产点：所有吞注释位置走同一例程

parser 在**每个会吞注释的位置**调用同一个"把注释交给当前最内层节点"
例程：

- `parse_token` 匹配后（现 `collect_following_comments` 位置，保留）
- production 边界 skip（现 `prepare_production` 吞注释的位置，改挂节点
  而非 `_line_comment_anchors`）
- pratt 前缀位与 operator 消费后（现 `comment_sink` → anchors，改收集
  到将构造的表达式节点）

### 3. 唯一消费点：renderer 按 layout 元素序列 + gap 标签渲染

renderer 只消费同一份元信息：在节点 layout 元素序列中按 gap 标签插入
注释。删除普通注释的 `restore_comments` / `restore_line_comments` 通道
（`renderer/inline_comment.py` 仅保留 tpc marker 用途的 only_tpc 分支）。

### 4. "最内层"精确定义 + 独立行注释形态

- **最内层** = 直接覆盖该 token 间隙的最小语法节点。对 `=` 与 RHS 之间
  → AssignStmt（`=` 是它 production 的字面 token，无更小节点包住）；
  对 `+` 与 `b` 之间 → BinaryOp。
- **结构上不相关就上挂**：间隙两侧不属于同一最内层节点（`;` 后接下条
  语句、端口列表 `,` 分隔的两个端口）→ 挂共同祖先（容器/块节点），
  gap 标签 = `between_child_i_and_i+1`。现 `_comment_anchors` 的
  "语义属于前一组（trailing）"启发式即此规则的模糊版，落为显式标签。
- **独立行注释保留 Comment 一等子节点形态**（block 层子节点，结构序
  天然保序、变换随子树走）；元信息槽位只管行中/行尾/间隙注释，不并入
  leading 槽位（决策 2026-09-04）。

### 5. pratt 注释挂载到表达式节点本身

operator 间隙注释（`a + /* c */ b`、`cond ? /* 真 */ a : b`、一元前缀
`- /* c */ a`）在 pratt 循环跳过时收集，于 BinaryOp / TernaryOp /
UnaryOp 节点构造完成后挂到该节点（gap = op 与 right/operand 之间）。
renderer 在这些节点的布局消费 op 间隙注释（决策 2026-09-04：挂表达式
节点本身，不逐级上挂语句节点）。

### 范围边界

- **tpc marker 维持独立通道**（决策 2026-09-04）：`/*<tpc:*>` 是
  预处理器跨阶段产物，渲染后 protect_and_reverse 需按 marker 定位还原，
  生命周期与源注释不同，不并入注释单机制。
- **变换路径**：`migrate_comments` 已是结构级（deep 收集槽位随替换走），
  与单机制同向，保留。
- **formatter（世界 B）品类对齐对行中块注释无防护**（2026-09-04 实测
  发现，关联观察非本 ADR 范围）：`reg [31:0] counter /* decl comment */;`
  与相邻声明成组时 `[31:0]` 被挪进注释文本——`column_align` 单声明路径
  无 `/* */` 注释 token 防护。单机制落地后 formatter 消费/绕行注释的
  方式需同步评审（列入实现前置检查）。

## 权衡

- 付出：parser 收集协议重构（吞注释位置收敛单例程）+ pratt 注释收集
  上挂 + renderer 消费端 gap 渲染 + 删除普通注释回插通道 + 相关测试迁移。
- 换回：消除"渲染端删槽 + restore 去重"双份防护；消灭 anchors 的
  ±3 行窗口启发式（锚点漂移即丢/错插/非幂等振荡三类已知缺陷根除）；
  pratt 内注释从"渲染后字符串级回插"升为结构序，变换/重排随结构走。
- 被拒绝备选：
  - 修修补补保持双轨（各通道加防护）：复杂度不降反升，机制分裂依旧。
  - pratt 注释逐级上挂语句节点：renderer 改动小但注释与表达式结构脱钩，
    违背"最内层"语义。
  - 独立行注释并入 leading 槽位：消灭子节点形态需重做 block 渲染与
    变换迁移，改动面大、收益低。
  - tpc marker 并入注释机制：预处理器/渲染还原管线整体重构，超出范围。

## 验证

- 既有注释测试全绿（不丢注释/不漂移/幂等）：
  `test_comment_attachment.py` / `test_comment_slots.py` /
  `test_comment_migrate.py` / `test_pratt_comment_keep.py` /
  `test_comment_restore.py`（新增 e2e 门禁，样本级直接断言文本，
  补 pratt operator 间隙注释用例——此前 e2e 样本无此形态）。
- e2e 样本：`run_all_tests.py normal comments|inline_test`（保真 1.0）。
- 全量回归：pytest tests/ + real corpus（保真度守卫）。

> Impl: 待实现（parser/parser_core.py::Parser 注释收集收敛 →
> parser/_production.py::collect_following_comments 扩展 pratt 上挂 →
> parser/pratt_parser.py::parse_expression 收集接口 → renderer 消费端）
> Test: tests/e2e/test_comment_restore.py（新增）+ 既有 4 个注释测试文件
