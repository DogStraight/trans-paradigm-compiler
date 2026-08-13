# TODO（纯待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 完成基线（当前验证过的事实）：
> - 549 测试全过；PicoRV32 token 完整硬基线（format 不改 token）
> - c4 第二语言完成（.c → c4 VM 汇编，6 集成测试）——语言无关主张实证
> - formatter 已接入管线（format_output 默认 True），67 单测 + 幂等回归
> - 预处理器宏相关完成（带参宏/条件编译还原/指令原位回插，e2e 守卫 12+ 项）
> - typed_ports 增强渲染双路径（展开/保留，expand_enhanced 开关）
> - 数字形态配置化完成（声明→FSM 生成器 + 语言包声明 + signed 's + 0'b1 标准拒绝）

## P1 — Verilog 实例完善

### P1.1 预处理器单元测试（primitives 级）

- [ ] 指令原语/宏展开/ifdef 分支/逆向恢复逐部件单测
      （e2e 宏还原测试已有，缺 primitives 级）

### P1.3 formatter 补齐（实用缺口）

- [ ] **宽度控制折行**：独立 pass，indent 后——检测超宽行（max_line_width 可配），
      在运算符/逗号断点拆行 + 续行 +1；复用 multi_line_cont 机制；不改 token，幂等锁
- [ ] **SystemVerilog 基础覆盖**：logic/always_ff/always_comb 关键字 + 基础语法
- [ ] **风格参数化**：缩进宽度 / tab vs 空格 / `[ 3:0]` 高位空格 / 运算符周围空格
      进 formatter tpc.toml

### P1.4 增强渲染补充

- [ ] 验证补充：typed_ports 更多样本（nested/invert）在 expand_enhanced=True/False
      两路产出可读文本 + token 完整 + format 幂等

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
