# ADR-0016: 宏体入树——raw 源区间权威 + 展开分级投影 + 对应层（draft）

- Status: draft（0.1.2 立项设计输入；实施阶段见 `TODO.md` 0.1.2 节）
- Date: 2026-09-11
- 承接：P3.6（ROADMAP，宏体形态分类 + 宏节点进 AST）+ `_drafts/macro-into-tree-design.md`
  （设计收敛稿）；调研来源（Lean 4 / Verible / Clang / GLR 机制对照）落
  `docs/references.md`。

## 背景

现状：宏一律**全展开**（宏体替换后不进 AST）。原意图带宏节点进 parse，但
**残缺片段宏**（`= 1'b1` / `[3:0]` / 半截 `begin`/`end`）会破坏 token 与语法
边界 → parse 失败 → 只能全展开。后果：

- 宏边界丢失 → P3.3 双向映射（源文本 ↔ 展开后 token）无锚点
- AST 与源文本错位 → P3.2 增量 diff 无法局部定位（涉及宏的编辑全量失效）
- 展开量大 → 渲染还原靠 anchor/残片启发式（脆弱）

## 决策

**统一模型：raw 源区间权威 + 展开 = 区间上的分级投影 + 对应层。**

1. **raw 源区间是唯一权威**——源文本永不漂移，从不被展开结果回写。
2. **任何宏（文本/结构、完整/残缺）= 源上的一个区间 + 展开配方**；统一单位是
   **源文本区间**，不是树节点（节点只是"完整单元宏投影独立"的特例）。
3. **展开 = 区间上的分级投影**（按需、一次性）：
   - **完整单元宏** → 宏体 token 级替换 → 可独立成节点（可缓存）
   - **残缺宏** → 宏体**文本**替换调用点文本 → 重新 lex → 融入父结构
     （残缺宏破坏 token 结构，故只能在文本区间投影；破坏只发生在一次性副本里，
     raw 不受影响）
4. **渲染直接走源区间**（raw 保真天然，无还原问题）；**语义需要时才投影**。
5. **对应层**存"区间 ↔ 展开 ↔ 定义"的对应关系（可重算的不存储：raw 从源切片、
   expanded 是确定性函数），供诊断/增量/双向映射。

**形态分类**是投影粒度选择的前置：完整语句/声明/表达式 → token 级；
残缺片段 → 文本级。分类器 = 包装解析（stmt/decl/expr/port 四包裹）+ 首 token
续接预过滤。

**包装模板是语言语法知识**——按 proc_assign_rules 先例进 grammar TOML 协议字段
（如 `macro_hygiene_wrappers`），引擎只做通用执行器，不硬编码。

## 权衡（被否决的备选）

- **双路进树**（宏节点挂 raw 串 + expanded 影子子树）：树只有一个骨架，children
  只能连一个结构 → 双路必然退化为"一主一引用"；双份物化 = 存储膨胀 + 同步漂移。
- **句级路径分叉**（raw 句 + expanded 句并列 sibling）：选路负担推给每个 AST
  消费者（破坏"普通遍历者无脑递归"）；且只覆盖整句宏，表达式宏（Verilog 主力）
  进不来。
- **展开 parse + 还原**（现状）：把展开结果当渲染对象再还原，是渲染面选错的
  妥协产物。

## 实施阶段（0.1.2，每阶段可独立验证）

0. **P3.1 span 绑定**（前置）：`rule_node.tok_span`（起止 token_pointer）+ 回溯回滚；
   可选 pratt 原子绑位置
1. 形态分类器（✅ 已实现：`preprocessor/macro_shape.py` + `tests/engine/preprocessor/test_macro_shape.py`）
2. MacroCall 节点入 AST + 包装模板进 grammar TOML 协议字段
3. linter 同步（形态判定同一份配置，避免双实现漂移）
4. 管线后端适配：宏调用位 vs 展开体位 span 语义区分、语义检查穿透展开体
5. 真实语料验证（ice40 / picorv32）+ 幂等/保真不回归

## 验证

- 分类准确率（真实语料）+ 原型转正
- 宏节点保留 + 展开量下降 + 幂等/保真不退化
- 全量 pytest 绿 + e2e FAIL 0

## 关联

- 前置/后续：P3.2（增量重解析）/ P3.3（双向映射）/ P3.4（增量 check）——宏节点
  保留是增量 diff 结构对齐的前提；P3.5（Rust 下沉）依赖 P3.1 接口稳定。
- 相关：ADR-0015（管线时点化——宏入树带来的管线后端变动与其一并实现）。

> Impl: `core/define.py`（`Node._tok_span`）+ `parser/_production.py`（span 写入，阶段 0）；
>   `preprocessor/macro_shape.py`（形态分类器，阶段 1）；其余待实现
> Test: `tests/languages/verilog/test_tok_span.py`（阶段 0）+
>   `tests/engine/preprocessor/test_macro_shape.py`（阶段 1）；真实语料待阶段 9
