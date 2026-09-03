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

### 1. 唯一数据面：注释 = 节点元信息 + 节点内位置

每条源注释挂在某个 AST 节点的元信息属性上（沿用 `_comment_slots`
下划线属性族，normalizer 保留、dump 过滤），携带**节点内位置**而非
"走 parser 旁路列表"。

**实现细则（2026-09-04 落地前修订）**：ADR 原拟"gap 标签（before_first /
between_element_i / after_element_i）"以 layout 元素序为坐标——但 parser
只有 **production 元素序**（token/@call 序列），renderer 只有 **layout
元素序**（TOML 声明，可重排/省略/合并 token），两者不同构；无 P3.1
token span 绑定前，parser 无法生产 layout 元素序标签。**唯一可由 parser
生产、renderer 可解的坐标 = 锚 token 内容**（注释前 token），即现存
`inline_after` 协议：`_comment_slots["inline_after"] = {锚token内容: [(注释,
源行号)]}`。消费端 = renderer 在该节点 layout 元素序列里定位锚（见决策
3）。文本重复歧义（同行多同文 token）与"锚不在 layout 字符串元素里"
为已知边界（P3.1 span 绑定后升 gap 标签消歧，另案，与 references.md
「pratt 前缀吞注释」边界同源）。

`//` 行注释的"必须断行"语义：行尾形态（注释后同行无代码）**不挂
inline_after**（行中断行会吞后续代码）——行尾注释走 trailing/attachment
槽位（LineSuffix 行尾锚定），与现状一致（`parser/_production.py`
collect_following_comments 的 is_midline 判定即此分界）。

### 2. 唯一生产点：所有吞注释位置走同一例程

parser 在**每个会吞注释的位置**调用同一个"把注释交给当前最内层节点"
例程：

- `parse_token` 匹配后（现 `collect_following_comments` 位置，保留）
- production 边界 skip（现 `prepare_production` 吞注释的位置，改挂节点
  而非 `_line_comment_anchors`）
- pratt 前缀位与 operator 消费后（现 `comment_sink` → anchors，改收集
  到将构造的表达式节点——**阶段 A 落地点**，见决策 5）

### 3. 唯一消费点：renderer 按锚定位插入

renderer 只消费同一份元信息：在该节点 layout 元素序列中按**锚 token
内容**定位插入点（line 原语消费 inline_after：元素文本含锚即后插，
消费后删槽防双份）。删除普通注释的 `restore_comments` /
`restore_line_comments` 通道（`renderer/inline_comment.py` 仅保留 tpc
marker 用途的 only_tpc 分支；`comment_restore.collect_inline_after_leftover`
随结构轨全覆盖后移除）。

### 4. "最内层"精确定义 + 独立行注释形态

- **最内层** = 直接覆盖该 token 间隙的最小语法节点。对 `=` 与 RHS 之间
  → AssignStmt（`=` 是它 production 的字面 token，无更小节点包住）；
  对 `+` 与 `b` 之间 → BinaryOp。
- **结构上不相关就上挂**：间隙两侧不属于同一最内层节点（`;` 后接下条
  语句、端口列表 `,` 分隔的两个端口）→ 挂共同祖先（容器/块节点），
  锚 = 前 token（如 `;`/`,` 本身无更小节点，挂语句/列表节点 trailing
  语义）。现 `_comment_anchors` 的"语义属于前一组（trailing）"启发式即
  此规则的模糊版，落为显式归属。
- **独立行注释保留 Comment 一等子节点形态**（block 层子节点，结构序
  天然保序、变换随子树走）；元信息槽位只管行中/行尾/间隙注释，不并入
  leading 槽位（决策 2026-09-04）。

### 5. pratt 注释挂载到表达式节点本身

operator 间隙注释（`a + /* c */ b`、`cond ? /* 真 */ a : b`、一元前缀
`- /* c */ a`）在 pratt 循环跳过时收集，于 BinaryOp / TernaryOp /
UnaryOp 节点构造完成后挂到该节点 `_comment_slots["inline_after"]`，
锚 = operator token 内容（`+`/`?`/`:`/`-`）。renderer 消费端需扩展
line 原语的锚匹配：除 layout 字符串元素外，**ref 元素求值后若为单一
文本且含锚也命中**（BinaryOp layout `line=[{ref=left}," ",{ref=op}," ",
{ref=right}]` 的 op 是 ref 不是字符串元素——这正是"pratt 内注释无文本
锚"的根源，扩展后结构序轨即可覆盖，无需 anchors 回插兜底）。（决策
2026-09-04：挂表达式节点本身，不逐级上挂语句节点。）

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

## 实施记录（分阶段，每阶段独立验证 + 提交）

### 阶段 0（已实现，2026-09-04，3e155b7）：删指纹回注老机制

作者决策：`--inline-comments`（70085f4 源 token 指纹 + 渲染后全量回插）
不稳定且消耗大，删除。范围：pipeline inline_comments 参数/字段/配置键、
restore_all_comments 全量回插分支（固定两态：展开 only_tpc / 非展开
only_midline）、tests/e2e CLI 与 run_all 模式、docs/api.md 配置说明。
验证：renderer/pipeline/注释/e2e 220 + policy 39 + run_all OK。

### 阶段 A（已实现，2026-09-04，c8334aa + 766d600 + 813d47e）

pratt operator 间隙注释上挂表达式节点（决策 5）——核心缺口闭环：
注释从"只存在于 parser._comment_anchors"升为 BinaryOp/TernaryOp/UnaryOp
节点 `_comment_slots.inline_after`；renderer line 原语锚匹配扩展 ref
属性值。验证全绿（注释/pratt/linter/real 语料 + run_all）。

补充验证（2026-09-04）：
- 合成层语言无关单测（766d600）：pratt_parser 直接以纯 token 流验证
  infix/多间隙嵌套/前缀一元/三目 op1+op2 双锚挂载、行尾注释不上挂走
  sink、sink=None（linter 场景）不崩——不依赖 verilog 语法。
- 复杂形态探针：括号内 `(a + /* c */ b)`、三目链中段、一元套括号、
  选择表达式后、长表达式折行——全部结构序消费（anchors 空、位置精确、
  幂等）。
- 同语句双机制叠加：`assign x = /* =后 */ a + /* +后 */ b`——parse_token
  间隙（挂 AssignStmt）与 pratt operator 间隙（挂 BinaryOp）产同一
  `_comment_slots.inline_after` 协议，renderer 同一消费，幂等 ✓。
- migrate_comments dict 槽位修复（813d47e）：阶段 A 引入 inline_after
  dict 后，变换替换含注释表达式子树时原实现 extend(dict) 丢注释内容。
- 已知边界（非回归）：pratt 内 `//` 行尾注释（`a + // 行尾\n b`）错插
  吞代码——阶段 A 前后行为一致（既有 restore 边界缺陷，references.md
  「同行多注释局限」相邻），目标④删 restore 通道后的处置另议。

### 阶段 B 前置（已实现，2026-09-04，756dcdf）

锚点收集端去重（`_record_anchor`，按通道分 key 空间）：parser 回溯对
同一注释重复收集（real 语料实测 _comment_anchors 447→427、
_line_comment_anchors 441→335，picorv32 端口组注释被候选规则回溯收集
4 次）。restore 端本就按 (text,line) 去重保留首条锚——收集端同语义
去重，渲染行为完全等价。

### 阶段 B 调研结论（2026-09-04，作者决策已定）

`_line_comment_anchors`（prepare_production 吞注释，real 语料 unique
335 条）形态实测：**独占行注释 322 : 行尾 13**——即绝大多数是列表
结构内（端口组间/参数列表/语句列表）的独立行注释（如 picorv32
`// Look-Ahead Interface`），与 block 层 Comment 一等节点同构但**缺
容器节点可挂**（repeat/seq 结构内无 block_node）。改挂节点有两个硬
障碍（2026-09-04 探针确认）：
1. **回溯语境挂载目标不稳定**：prepare_production 在每个 production
   尝试前吞注释（候选规则逐一尝试 ×4），current_node 是尝试中的
   rule_node、可能失败回滚——注释不能挂到未确认成功的节点（这正是
   parser 级列表存在的理由）。
2. **归属语义需逐类定义**：独占行注释在两组之间，语义属前一组
   trailing 还是后一组 leading 需人工判定（restore 现有启发式偏
   trailing/上方，未必正确）。

**作者决策（2026-09-04）**：注释**全进树**，无例外——行注释与块注释
（独占行形态）作为 **Comment 节点**挂载（结构清晰、可作一等子节点），
行内注释/行尾注释作为**语法节点元信息**（_comment_slots/inline_after
等）；同时**删除指纹回注老机制**（`--inline-comments`，70085f4 遗留，
不稳定且消耗大，已随 3e155b7 删除）。阶段 B 的独占行注释按此决策应
挂载为 Comment 节点——技术路径：吞注释时挂到**容器节点**（含列表的
block/规则节点）的 sub_node 作为 Comment 子节点，而非 parser 级旁路
列表；回溯稳定性问题以"成功确认后挂载/容器级收集"解决（实现详见
阶段 B 实现小节，待落地后补）。

### 阶段 B 技术方案（2026-09-04，renderer 缺口已实测）

独占行注释的宿主是 **repeat 列表容器**（PortList.items /
DeclaratorList.items / 语句列表等），容器规则成功后确定。实现分两段：

**B1 parser 侧**：repeat/seq 迭代间隙被吞的独占行注释（comment→newline
形态，即"独立行注释"判定同 collect_line_comments），在容器规则**确认
成功后**转为 Comment 子节点插入容器 items 对应位置（源序保持）。回溯
稳定性：吞注释暂存容器级 pending，容器成功后按 token 位置归位；失败
回滚时 pending 随容器丢弃。这替代 `_line_comment_anchors` 旁路列表。

**B2 renderer 侧**（缺口已实测）：join/intent 原语的 items 列表现把
Comment 节点当普通项用分隔符连接（`input a, // comment, output b` 错）——
需识别 Comment 节点：不参与分隔符、独立行渲染（`// comment` 独占行，
不吞后续项）。Comment 已有布局（ref=value），join 遇 Comment 项插入
Break 而非分隔符。

验证门槛：real 语料 335 条独占行注释渲染位置与 restore 现状一致
（保真不降）+ 幂等 + 既有注释测试全绿。

### 阶段 B 实施进展（2026-09-04）

**B2 已完成（d34100a）**：join 识别 `_comment` 标记项独立行渲染——
parser collect_line_comments 构造 Comment 节点挂 `_comment` 引擎标记
（语言无关下划线属性），join 遇注释项作段分隔（前项逗号归属行尾 /
注释独立行 / 后项新段首 / 尾注释无空行）。6 单测 + renderer/yaml/
verilog 538 全绿。

**双捕获冗余消除（进行中）**：real 语料实测 line_comment_anchors
441 raw → 250 unique，其中 **171 条已在 AST 有 Comment 节点**（block
body 独立行注释被 collect_line_comments 收走，但 prepare_production
回溯先吞进 line_anchors——restore existing_lines 本会跳过已渲染注释，
条目纯冗余）。修法：collect_line_comments 收 Comment 时
`_mark_comment_collected` 登记 seen + 移除已存在的 line_anchor 条目。
量测：441 → 132（消除 70%），real fidelity 门禁 47 passed 无保真下降。

**B1 待设计**：34 条真容器缺口（端口列表/实例端口组间，serv_top 26 条）
——注释在 repeat 结束后被上层声明规则吞（PortList repeat 的 seq
`comma` 前遇注释失败→repeat 提前结束，注释成上层残留），收集点不在
repeat 层。需"repeat 遇独占行注释续行"核心语义设计（见调研结论障碍
1/2），或维持 restore 通道作为已知边界。与作者对齐中。

### 阶段 B1 实现记录（2026-09-05，工作区待提交）

**设计收敛（实测驱动，推翻草案的 iter 级 pending 方案）**：草案 A/B
（repeat 迭代前检查、迭代内 slice 上浮）实测错位——注释在**嵌套失败
迭代**（如 `input a, // State\n output b` 的 `// State` 在 a 的
DeclaratorList 尝试 `, b` 时被 Declarator 规则吞）被吞，iter 级 slice
把注释归错迭代（Data 型注释被挂到前一端口前）。规则级 pending 领取
（挂 leading 槽）也被内层 DeclaratorList 抢领错位。

**定案：行号窗口上浮（_repeat_loop）**：
1. `prepare_production` 吞注释时判定**独占行**（`_is_line_only_comment`
   向前扫描前一非空白 token 是否 newline/文件首），line 通道条目附加
   `line_only` 标记；tpc marker（`// <tpc:*>`）排除（only_tpc 通道，
   宏/条件块还原依赖，不进树）。
2. `_repeat_loop`（parse_repeat/parse_plus，**parse_optional 不 lift**——
   optional 单值槽上浮会挤占内容致端口丢失）每次迭代成功后，按**源行号
   窗口**（上一迭代匹配末行 < 注释行 ≤ 本次迭代匹配末行）取 line 通道
   独占行注释，上浮为 Comment 迭代项插本次迭代结果之前（nodes 源序即
   容器 items 序）；`_mark_comment_collected` 移除条目防 restore 双份
   （restore existing_lines 已渲染跳过另有兜底）。
3. 绑定层 list-spec 提取 `keep_comments`：`items[*].sub_node[N]` 遇
   `_comment` 标记项解析 None 时保留 Comment 项自身进容器 items——
   renderer join（B2）识别 `_comment` 项独立行段渲染。

窗口语义解决嵌套失败迭代的归属错位：注释行在 a 行与 b 行之间 → 由
PortList 的 b 迭代窗口收走（挂 b 前）；b 行尾逗号后的注释行 > b 行 →
留给 c 迭代。行号固定只落一窗口（区间递增不重叠）→ 不重复上浮。
repeat 起点行作下界：本 repeat 之前元素（repeat 外）吞的注释不归属
容器，且嵌套 repeat（DeclaratorList）起点行在内层不误收外层项间注释。

**实测收益**（expand_macros=True 渲染，B1 前宏场景 line 通道 only_tpc
不回普通注释 → 容器注释丢失）：
- serv_top：26 → 54 条保留（55 源注释，唯一缺失为 `(//RF interface`
  行内形态，非独占行——B1 范围外既有边界）；
- tv80_core：480 → 509（+29）；
- picorv32：100 → 100（无损失）。

**已知边界**：容器**首元素前**的独占注释（如 `module m (// ok` 后首端口
前）与行内/行尾形态不进 B1（optional 不 lift / line_only=False），仍走
line 通道时域回插；`(//RF` 行内实例端口组注释为既有 restore 边界。

**新增门禁**：tests/e2e/test_comment_container.py（PortList /
NamedPortList / DeclaratorList / CaseItemList 项间独占注释 → Comment
节点进 items + 独立行渲染 + 幂等，5 测试）。

### 阶段 B1.1 块结束符行尾注释进树（2026-09-05，工作区待提交）

**缺口**：块规则（BeginEnd/CaseStmt 等）结束符（`end`/`endcase`）后的
行尾注释（`end // case: 8'b00001010`）在 try_block_rule 只记 inline
anchor——restore_comments 仅回 midline/tpc（非展开 only_midline /
展开 only_tpc 均跳过行尾普通注释）→ 行尾注释**永远丢**（tv80 实测 139
条 eol 缺失，非宏/宏场景均丢）。

**修法**：try_block_rule 消费 block_end 后注释时，**行尾形态**（注释与
结束符同行）挂块规则节点 `_comment_slots["trailing"]`（render_node
LineSuffix 结构序渲染，与 attachment 同轨）；独占形态（结束符后新行）
保持现状 inline anchor（属下一元素前）。

**实测收益**（expand 渲染）：tv80 eol 缺失 139 → 5（+134 保留；总注释
保留 509 → 670，src 724）；serv_top 54/55、picorv32 100/100 保持。
残余 5 条为宏条件区语句行尾注释（attachment 在宏展开路径的行号漂移
缺陷，既有边界，非本修复范围）。

**门禁**：tests/e2e/test_comment_container.py::TestBlockEndComments
（2 测试：end 行尾注释保留 + 幂等）。

### 阶段 B1.2 删除 line 通道普通注释回插（目标④，2026-09-05，工作区待提交）

**度量**（删除决策数据）：41 文件（normal 32 + real 9）渲染
`enable_line_comment_restore` 开/关对照——输出注释行差仅 **1 条**
（tv80），且该条是 restore **锚点错插缺陷**（`// Outputs` 被插进
`reg [7:0] Q;` 声明中间）——删除后该注释不恢复但结构干净（净改善）。
B1/B1.1 后普通独占行注释全部进树（容器项间 Comment 迭代项 / 块结束符
trailing / block body Comment 节点），line 通道普通回插残余归零。

**删除**：restore_all_comments 移除 `enable_line_comment_restore`
参数与全量普通回插分支——line 通道恒 only_tpc（宏/条件块 marker 回插，
protect_and_reverse / restore_condition_blocks 还原依赖）；pipeline
ctx 字段 / run_pipeline_on_source 签名 / run_all_tests 传参同步删除
（不留兼容垫片）。

**待后续清理**：restore_line_comments 函数体仅剩 only_tpc 调用路径，
函数内普通注释窗口回插分支（is_tpc=False 路径）成过渡残留（改动面大
且与 tpc 插值逻辑交织，本轮未深清——功能不可达）。

### 阶段 B 小结（2026-09-05）

| 项 | 内容 | 实测 |
|---|---|---|
| B2 | join 识别 Comment 项独立行渲染（d34100a） | verilog/yaml 538 全绿 |
| B1 | 容器项间独占注释行号窗口上浮（c8b3a57） | serv_top 26→54、tv80 +29 |
| B1.1 | 块结束符行尾注释挂 trailing（cb53d75） | tv80 509→670 |
| B1.2 | 删除 line 通道普通注释回插（目标④主体） | 41 文件差 1（错插），删除净改善 |
| B1.3 | 容器首元素前独占注释挂 Comment 子节点 | head comment 保留 + 幂等 |
| B1.4 | 删除 inline 通道 midline 回插（目标④完成）+ join 分隔符锚 | normal 组零丢失、corpus 无变化 |

### 阶段 B1.3 容器首元素前独占注释进树（2026-09-05，提交 9733c9f）

**回归暴露**：B1.2 删除 line 通道普通回插后，容器**首元素前**的独占
注释（`module m (\n // head\n input a`——首元素非 repeat 迭代项，不在
B1 行号窗口）无兜底 → 丢失（实测 `// head comment` 渲染后消失）。

**修法**（_starts_line + _claim_head_comments）：
1. 行首开始的规则（`_starts_line`：规则入口 token 前一非空白/非注释
   token 是 newline）成功时，把 line 通道中"行 < 本规则匹配末行"的独占
   注释领挂 **Comment 子节点**（sub_node 首位——ADR 模型独立行注释 =
   Comment 节点，非 leading 元信息）；
2. 领窗口 = 匹配**末行**（规则入口 peek 可能捕获被吞的注释 token，行号
   偏小；规则内容之后的注释如 b 行尾逗号后 `// Data` 行 > b 末行留给
   后续规则，源序正确）；
3. **repeat 迭代深度协调**：迭代项规则（行首）在 _repeat_loop 迭代内
   （_repeat_iter_depth > 0）不 claim——迭代项间注释由 B1
   _lift_gap_comments 上浮为 Comment 迭代项（ADR 模型优先，mark 互斥
   不双份）；optional 单值槽（PortParens `@PortList?`）不算迭代项上下文
   （否则首元素 claim 被误拦）；首元素前注释由**容器首元素规则**领
   （行 < repeat 起点，B1 窗口外）✓；
4. renderer join：item sub_node 首部 Comment 拆为注释段独立行渲染
   （与 B2 is_comment 段同语义；首注释段前硬 Break——first_soft 空格
   会把注释贴到父行尾如 `module m( // head`）。

**门禁**：tests/e2e/test_comment_container.py::TestContainerHeadComments
（2 测试：模块头/实例端口首元素前注释保留 + 幂等）；join 首注释段
Break 语义测试期望更新（test_comment_at_head 等 3 用例）。

### 阶段 B1.4 删除 inline 通道 midline 回插（目标④达成，2026-09-05，工作区待提交）

**度量**（正确 patch——直接替换 comment_restore 模块内 restore_comments
引用，前次实验 patch 错对象无效）：normal 组 32 文件禁用 midline 回插
后仅 ref_inline_test 1 条丢（`/* port comment */`——PortList join 分隔
符 `,` 后的行中注释，`,` 非布局 line 文本元素 line.py 锚消费不到）。

**渲染补全（③）**：join 原语消费容器节点 inline_after 中锚=分隔符的
行中注释——按收集序（= 分隔符序）逐 sep 分配插到分隔符后（折行前），
pop 直接作用于节点槽（消费即删防 leftover 双份），残余留给兜底。

**删除**：restore_all_comments 移除非展开路径 midline 分支（inline 通道
仅剩展开路径 only_tpc）+ pipeline collect_inline_after_leftover 调用与
函数删除（渲染后补锚无消费通道）。

**验证**：normal 32 文件 midline 删除前后输出一致（ref_comments /
ref_inline_test identical）；real corpus（展开场景 midline 本就 only_tpc
过滤）缺失数前后完全一致（serv_top 1 / picorv32 0 / tv80 13 / darkriscv
12，均为既有边界）；全量 pytest 1540 + run_all normal 32/real 9 OK。

**目标④达成**：普通注释的 restore_comments / restore_line_comments
回插通道全部删除（line 通道 B1.2、inline 通道 B1.4）——仅剩 tpc marker
独立 only_tpc 通道（宏/条件块还原依赖）。

### 阶段 B1.5 清理 restore 函数普通分支残留（2026-09-05，工作区待提交）

restore_comments / restore_line_comments 原 only_tpc / only_midline
参数与其普通注释分支（only_tpc=False 窗口匹配、midline 过滤等）在
B1.2/B1.4 后无调用方（恒 tpc 语义）——删除参数与普通分支，函数**只
处理 tpc marker**（`/*<tpc:*>` 宏 marker / `// <tpc:*>` 条件占位）：
- restore_comments：删 only_tpc/only_midline 参数与 only_midline 过滤，
  普通注释条目（无 `tpc:`）直接 continue；tpc 块注释 marker 的锚窗口
  路径保留（原逻辑服务 tpc 非 midline 条目）
- restore_line_comments：删 only_tpc 参数与 is_tpc=False 普通锚匹配
  大段（短符号锚/精确锚/端口行首锚定的 ~80 行），保留 tpc 词边界匹配
  + 插值定位 + 相邻顺序保持
- comment_restore 调用同步（不再传 only_tpc=True）

验证：tpc 还原面（macro_reverse / real_fidelity / real_corpus 的
darkriscv/tv80/ice40 宏与条件块）101 测试通过 + run_all real 9/9 +
全量 pytest 1540 全绿。

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
  `test_comment_restore.py` + `test_comment_container.py`（B1 门禁，
  容器项间/首元素前/块结束符注释 + 幂等）。
- e2e 样本：`run_all_tests.py normal comments|inline_test` + normal
  全组 32 + real 全组 9（保真 1.0）。
- 全量回归：pytest tests/ 1540 passed + real corpus（保真度守卫）。

## 实施状态（2026-09-05，B1 系列完成）

| 阶段 | 内容 | 提交 |
|---|---|---|
| 阶段 A | pratt operator 间隙注释挂 BinaryOp/TernaryOp/UnaryOp（行中 inline_after 锚=op）+ renderer line.py ref 锚消费 + migrate 修复 | c8334aa / 766d600 / 813d47e / aedfa2f / 756dcdf / c00279f / 1e582f6 / a116b2f / b6e50dc |
| 阶段 0 | 指纹回注删除（老机制不稳定） | 3e155b7 |
| B2 | join 识别 Comment 项独立行渲染 | d34100a |
| B1 | 容器项间独占注释行号窗口上浮（Comment 迭代项） | c8b3a57 |
| B1.1 | 块结束符行尾注释挂 trailing | cb53d75 |
| B1.2 | 删除 line 通道普通注释回插 | b8ec648 |
| B1.3 | 容器首元素前独占注释挂 Comment 子节点 | 9733c9f |
| B1.4 | 删除 inline 通道 midline 回插（④达成）+ join 分隔符锚 | c02f6d7 |
| B1.5 | restore 函数清理为纯 tpc 通道 | 05524a3 |

目标五条达成情况：
- ① 吞注释位置收敛 + 注释进树：pratt op 间隙（A）、容器项间（B1）、
  首元素前（B1.3）、块结束符行尾（B1.1）、block body（既有 collect）；
  独立行注释 = Comment 节点（容器 items / 首元素 sub_node / block body），
  行内/行尾 = 节点元信息（inline_after / trailing）
- ② pratt 注释挂表达式节点：行中 ✓（A）；行尾 op 间隙注释维持
  comment_sink 语义（ADR 决策 5 记录的边界——多行表达式 broken 行尾
  渲染语义未立项）
- ③ renderer 布局锚消费：line.py 文本/ref 锚（A）+ join 注释段（B2）+
  join 分隔符锚（B1.4）
- ④ 普通注释 restore 通道删除：调用面（B1.2 line / B1.4 inline）+
  函数体纯 tpc（B1.5）；tpc marker 独立通道维持（作者决策）
- ⑤ inline_after/trailing/leading 槽兼容 + migrate_comments 迁移：
  测试全绿

已知边界（ADR 决策 5 / 实施记录，均非本机制违背）：
- pratt op 后**行尾**注释（`|| // bgeu`）→ comment_sink（展开场景
  普通不回 → darkriscv ~5 条丢）
- 宏展开后行号漂移的 attachment 行尾注释（darkriscv/tv80 少数）
- `(//RF` 行内实例端口组注释（行内形态）
- restore_line_comments 函数体已纯 tpc（无普通残留）

> Impl: parser/pratt_parser.py（_skip_gap_comments/_mount_op_comments）+
> parser/_production.py（_is_line_only_comment/_lift_gap_comments/
> _claim_head_comments/try_block_rule trailing/行首规则领挂）+
> parser/attribute_binder.py（list-spec keep_comments）+
> renderer/primitives/join.py（Comment 段/首段 Break/sub_node 首 Comment/
> 分隔符锚）+ renderer/comment_restore.py + renderer/inline_comment.py
> （纯 tpc 通道）
> Test: tests/e2e/test_comment_restore.py + test_comment_container.py +
> 既有 4 个注释测试文件
