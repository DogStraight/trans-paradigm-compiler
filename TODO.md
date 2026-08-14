# TODO（纯待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 完成基线（当前验证过的事实）：
> - 587 测试全过；PicoRV32 token 完整硬基线（format 不改 token）
> - c4 第二语言完成（.c → c4 VM 汇编，6 集成测试）——语言无关主张实证
> - formatter 接入管线 + 幂等 + 宽度折行 + SV 基础覆盖 + 风格参数化 + 品类对齐
> - 预处理器宏相关完成（带参宏/条件编译还原/指令原位回插 + primitives 单测 19 项）
> - typed_ports 增强渲染双路径（展开/保留，expand_enhanced）+ nested/invert 验证
> - 数字形态配置化完成（声明→FSM 生成器 + 语言包声明 + signed 's + 0'b1 标准拒绝）

## P1 — Verilog 实例完善

### P1.3 SV 插件化（SV 语法做成插件，插拔动态适配）

> 来源：2026-08-13 用户方向——SV 基础已内嵌（logic/always_ff/always_comb 在
> verilog 语言包），但 SV 特性会持续增长（interface/class/struct/assertion 等），
> 内嵌会让 verilog 语言包膨胀。做成**独立插件**（如 plugins/sv）：
> 插拔动态适配——verilog 包按需挂载 SV 插件，接口/class 等新特性进插件不进主包。

- [ ] SV 插件骨架：plugins/sv/tpc.toml + 语法文件（token_ext/规则），
      verilog tpc.toml [plugins] enabled 控制挂载
- [ ] 迁移已内嵌的 SV 三样（logic/always_ff/always_comb）到插件
- [ ] 验证：挂载/卸载 SV 插件后 verilog 包行为正确（插拔无残留）

## P2 — 工程化收尾（发布准备）

### P2.0 机制可理解性

- [x] 配置生命周期评估 + 文档化（docs/config_lifecycle.md——三阶段时序 + 坑 + 评估结论保持注册制）
- [x] 表达式系统隐式约定文档化（docs/expression_conventions.md——优先级/atom/三元/一元）
- [x] 组件协议文档（docs/component_protocol.md——组件/槽位/原语/inject）
- [x] c4 定位为最小语言包模板（grammar/c4/README.md 模板路径 + 4 文档索引）

### P2.2 发布收尾

- [x] 覆盖率门禁（.coveragerc omit 入口/回退，fail_under=84，实测 84.57%）
- [x] 恢复 CI（.github/workflows/ci.yml：Windows + Python 3.11/3.12/3.13）
- [x] 安装可验证（pip install -e ".[test]" + tpc CLI 实测）
- [x] 补文档（CONTRIBUTING.md / CHANGELOG.md / docs/api.md）
- [ ] 覆盖率远期目标 ≥90%（当前 84.57%，需补 transform/renderer 等薄弱区）

## P4 — LLVM IR 前端桥（v0.2 商业向候选，非收尾）

> 来源：2026-08-14 用户方向。LLVM/MLIR 生态商业价值高（芯片/硬件厂商对
> "专有语言 → LLVM"定制付费意愿强），tpc 的配置驱动 + 模型代写正好能压
> 低这段最贵的前端成本。c4 已实证"语言 → 自定义 IR"（_asm.py 降 c4 VM
> 汇编），换靶为 LLVM IR 是同一件事。
>
> 定位：**不做"多级 IR 框架"（与 MLIR 撞车），做"语言 → 现成 IR 的前端桥"**——
> tpc 作为"任意 DSL → LLVM IR"的生成端，模型写变换插件组织降级管线。
> 用途也是"证明能力"的技术前提（对外 demo 靶子 = LLVM IR，厂商熟悉可接）。

### P4.1 LLVM IR 目标插件

- [ ] c4 增加 LLVM IR 输出插件（类比 `_asm.py`，c4 AST → LLVM IR 文本：
      define/load/store/br/icmp 等基础指令集）
- [ ] 与现有 c4 VM 汇编输出并存（同一语言多目标，验证"换插件换目标"）
- [ ] 验证：c4 小程序（if/while/函数调用）编译为 LLVM IR，`lli`/`clang` 可执行

### P4.2 对外证明能力（信任建立）

- [ ] 选一个垂直场景做端到端 demo（如 DSP 专有语言 / 硬件描述子集 → LLVM IR），
      配"配置驱动 vs 传统方案"的成本对比
- [ ] LLVM/MLIR 社区开源一个 tpc → LLVM IR 插件（技术背书路径）
- [ ] 技术博客/论文："配置驱动语言→IR"（可引用的专业形象）
- [ ] 从小而垂直的厂商切入（大厂有自研团队，小厂缺人决策快）

## P3 — 增量解析（v0.2 核心，非收尾）

> 来源：2026-08-14 用户方向。思路 = 复用已实证的"分段解析 + 并树"
> （tests/e2e/debug_segment_parse.py，PicoRV32 调试时验证过），把失效判定
> 从 module 级细化到语法单元级（近似 tree-sitter 的失效激活）。
> 目标：编辑 → token 级 diff → 延展到语法边界 → 仅重解析受影响单元 → 并树复用。

### P3.1 前置：AST 节点 token span 绑定（解析期）

- [ ] `_production.py` 构造 `rule_node` 时记录 token 范围（起止 `token_pointer`），
      存为 `rule_node.tok_span`（`Node` 用 `**kwargs` 接受任意属性，不改 `core/define.py`）
- [ ] 回溯（snapshot/restore）时 tok_span 正确回滚
- [ ] 方案 B（可选）：`pratt_parser.py` 原子（Number/Identifier 等）也绑 token 位置，
      粒度细化到表达式层

### P3.2 失效判定 + 增量重解析

- [ ] token 级 diff：新旧 token 流对比，标记变更 token（复用 lexer）
- [ ] 变更 token → 延展到语法边界（沿 `is_statement`/`is_block` 规则向外，到完整可重解析单元）
- [ ] 仅重解析受影响单元（`ParseContext` 从边界起始 token 驱动）
- [ ] 并树：替换 AST 中对应子树（类似 `merge_segments`，下沉到语句级）

### P3.3 已知坑：宏展开下的双向映射（2026-08-14 预判）

- [ ] **token span 对应的是"展开后"token，不是源文本**：源文本 → 预处理器（展开）→
      lexer → parser，AST 的 token 索引是展开后 token 流的索引
- [ ] 编辑 diff 在**源文本**上做，但 span 在**展开后 token**上——两边对不上，需映射层
- [ ] 预处理器已有反向资产：`preprocessor/_bridge.py`（锚 + 残片回插，marker 定位原文），
      renderer 靠它还原源码位置——增量需要**复用这套桥**，把"展开后 token → 源文本行"打通
- [ ] 条件编译（`ifdef/ifndef`）下编辑，会改变展开结果 → 整段缓存失效，需处理
- [ ] 宏定义本身的编辑（`define` 行改）→ 所有用到该宏的 token 全部失效，不是局部问题



## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
