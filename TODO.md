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

- [ ] 配置生命周期评估 + 文档化（declare_cfg 三阶段时序）
- [ ] 表达式系统隐式约定文档化（Pratt/operator 顺序/三元）
- [ ] 组件协议文档（插件层：register_plugin/transform 钩子/analyzer 原语）
- [ ] c4 定位为最小语言包模板（模型"从仿写到可代写"的增量路径）

### P2.2 发布收尾

- [ ] 覆盖率门禁（≥90%）
- [ ] 恢复 CI（.github/workflows/ci.yml；先移除 .gitignore 的 .github/）
- [ ] 安装可验证（pip install -e ".[test]"）
- [ ] 补文档（CONTRIBUTING / CHANGELOG / API）


## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
