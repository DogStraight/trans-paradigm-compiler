# 部件地图（Component Map）

> 模型/人想"先建立全局轮廓、再深入某文件"时读本表——**部件一句话 + 每文件
> 一句话**。与 `MODEL_INDEX.md` 分工：本表是**静态地图**（这个部件/文件是干嘛
> 的、和谁相邻），MODEL_INDEX 是**任务导航**（我要改 X 去看哪篇文档、哪个
> 实现、哪些测试）。读代码前先扫本表，动手前再查 MODEL_INDEX。
>
> **权威源 = 各模块 docstring 首行**：本表一行是 docstring 首行的摘录，
> 不重复正文。新增/重命名文件时同步本表该行（职责取 docstring 首行措辞），
> 保持薄层、不成为新负担。文件级详情看 `Doc:` 反引（文件头）与 MODEL_INDEX。

## 管线全景（阶段序）

```
lexer → (preprocessor 宏展开) → linter(预解析 token 级) → parser
      → analyzer(语义) → transform(变换) → renderer(文本) → (preprocessor 反向)
```

语言规则全部外置 `grammar/` TOML（语言知识不进代码）；引擎 = 通用骨架。

## parser — 语法：递归下降 + Pratt + 规则选择（tokens → AST）

| 文件 | 一句话 |
|------|--------|
| `parser_core.py` | Parser 主引擎：递归下降 + 回溯（`Parser.parse` 入口，块/普通链调度） |
| `_production.py` | 生产式匹配主循环（parse_token/call/seq/choice + 注释收集挂载） |
| `block_parser.py` | 块 & 语句级解析（行首规则领挂独立行注释 / Comment 子节点） |
| `pratt_parser.py` | Pratt 表达式解析（运算符优先级 + 行中/行尾注释挂载） |
| `rule_selector.py` | 候选规则过滤（start token 匹配）+ production 树序列化 |
| `follow.py` | FOLLOW 集派生（后继合法性，对标 yacc，end_case 已并入） |
| `attribute_binder.py` | `$N` node 绑定 & 路径提取 |
| `grammar_inject.py` | 语法规则注入（production 注入/传播/替换，树层结构化） |
| `_constants.py` | 包内共享常量（token 类型 re-export） |

## lexer — 词法：token 定义驱动扫描

| 文件 | 一句话 |
|------|--------|
| `main_lexer.py` | Lexer 主扫描器（token 定义驱动 + 行状态/缩进单位） |
| `capture_runner.py` | 配置驱动原始文本捕获（注释/字符串/块标量 token） |
| `number_gen.py` | 数字形态声明（`[[number.based]]`）→ FSM 转移表 |
| `number_runner.py` | 配置驱动数字解析（唯一路径） |
| `pre_scan.py` | 轻量预扫描（顶层声明符号收集） |
| `lexer_utils.py` | TOML 配置加载与合并工具 |

## linter — 前置 token 级 lint（反解析器，复用同一 TOML 语法）

| 文件 | 一句话 |
|------|--------|
| `scanner.py` | 两阶段 Linter 编排器（发现 + 扁平检查） |
| `discovery.py` | 发现阶段：token 流 → 自动注册的扁平检查器列表 |
| `checkers/` | 扁平检查器族（`matcher.py` 规则匹配 / `expression.py` pratt 复用） |
| `checker.py` | 扁平检查器协议、注册表与轻量 AST 节点 |
| `lookahead.py` | 动态两级前瞻消歧表 |
| `grammar_slicer.py` | 从语法规则推导切分层级映射 |
| `diagnose.py` | 条件编译多路径诊断（枚举所有路径逐条 lint 汇总） |
| `cli.py` | linter 诊断输出（CLI 入口） |

## preprocessor — 宏展开 / 反向映射

| 文件 | 一句话 |
|------|--------|
| `_expand.py` | 宏展开（strip 指令 + `` `NAME `` 引用展开） |
| `_reverse.py` | 宏反向（统一位置桥：锚 + 残片回插） |
| `_bridge.py` | 统一位置桥（Anchor Bridge）——锚 + 残片消耗式回插引擎 |
| `primitives/` | 指令处理原语（define/ifdef/include/undef 等） |

## analyzer — 语义分析：作用域、符号、类型 + 检查插槽

| 文件 | 一句话 |
|------|--------|
| `scope.py` | Scope（作用域链）+ Symbol（符号声明）类型 |
| `context.py` | AnalysisContext（分析上下文/诊断上报） |
| `traversal.py` | AnalysisTraversal（遍历 + post-pass 钩子调度） |
| `diagnostic.py` | 结构化诊断 + related 链 |
| `checker.py` | ProjectChecker（跨文件语义检查引擎） |
| `checks.py` | L1 声明式检查规则执行器（规则 = 数据） |
| `suppress.py` | 诊断豁免注释（Verilator lint_off 借鉴） |
| `primitives/` | 语义检查原语（symbol 声明/引用核对等） |

## transform — 语义映射 + 配置驱动变换（AST → AST）

| 文件 | 一句话 |
|------|--------|
| `engine.py` | AstTransformer + TransformPlugin 基类 + 自动注册（注释迁移 `migrate_comments`） |
| `config_driven.py` | 配置驱动变换（原语扩展：emit/expand/delete 等） |
| `_semantic_mapping.py` | 语义映射表构建 + 后处理管线 |
| `normalizer.py` | 统一的 AST 规范化层（结构保留） |
| `primitives/` | 变换原语 |

## renderer — Doc IR → 格式化输出（世界 A）

| 文件 | 一句话 |
|------|--------|
| `doc.py` | Doc IR（漂亮打印机中间表示）+ `layout()` 布局 |
| `renderer.py` | Renderer 主类（AST + 布局规则驱动 → 文本） |
| `node_renderer.py` | 节点级渲染（含 `_comment_slots` 槽位消费：leading/trailing/inline） |
| `loader.py` | TOML 布局规则 / 风格加载 |
| `inline_comment.py` | 锚点注释回注（纯 tpc marker 通道） |
| `comment_restore.py` | 注释回插编排 |
| `fidelity.py` | 保真度分级 |
| `primitives/` | Doc 原语（text/break/line/join/align/line_suffix/suffix_when…） |

## core — 引擎骨架：配置注册、错误、插件加载

| 文件 | 一句话 |
|------|--------|
| `define.py` | 核心类型：Token / GrammarRule / Node / FileManager |
| `config_registry.py` | 声明式配置注册中心（fail-fast 加载 + resolve） |
| `plugin_loader.py` | 插件加载与管理（capabilities / pass 声明 / postpass 收集） |
| `check_registry.py` | `[[checks]]` 声明式检查规则表（加载/校验/用户配置） |
| `token_protocol.py` | 引擎级 token 类型命名协议（单一事实源） |
| `_protocol.py` | 组件系统协议常量（统一 magic string） |
| `errors.py` | 统一异常层级 |
| `debug_report.py` | 失败现场报告工具（parser/linter 共用） |
| `global_state.py` | 引擎全局状态快照/还原（测试隔离，顺序无关） |
| `_user_config.py` / `utils.py` | 用户项目配置定位 / 通用工具 |

## pipeline — 管线编排

| 文件 | 一句话 |
|------|--------|
| `__init__.py` | 管线编排（`run_pipeline_on_source`，阶段序列化执行） |
| `schedule.py` | 编排调度（ADR-0007）：pass 声明 + 时点序列器 + 调度构建 |

## grammar — 语言规则（数据，不进引擎代码）

| 语言包/插件 | 一句话 |
|------|--------|
| `verilog/` | Verilog-2005 主体语言包（主包 = 可综合子集，发布基线） |
| `c4/` | 从零搭语言实例（迷你 C，产出汇编；language_walkthrough 教程主角） |
| `yaml/` | YAML 语言包（缩进 token 机制 + 块标量/plain scalar 验证） |

### verilog 插件族（`grammar/verilog/plugins/`）

| 插件族 | 一句话 |
|------|--------|
| `syntax/` | 语法扩展：sim（仿真语句）/ gates / nettypes / udp / specify / configs / attributes |
| `formatter/` | 世界 B：pass 管线 formatter（对拍 Verible，独立于世界 A） |
| `checks/` | 检查规则插件族：name/width/latch/unused/inst/hier/case/always/semantic（NC/W/AW 等码族） |
| `typed_ports/` | 自定义类型化端口（impl/type 声明 + 展开变换） |

## tests — 验证布局

| 目录 | 一句话 |
|------|--------|
| `tests/engine/<部件>/` | 引擎各部件单元/集成测试（与上各子包一一对应） |
| `tests/languages/{verilog,c4,yaml}/` | 语言实例测试（语法/格式化/命名/宏等） |
| `tests/e2e/` | 端到端门禁：保真（run_all normal/real 组）+ 注释 restore + 互操作 |
| `tests/differential/` | 与成熟工具对拍（Verible format / sv-parser 差分） |
| `tests/fuzz/` | 语法驱动 + 变异 fuzzing（不崩溃/token 保序/幂等不变量） |
| `tests/policy/` | 文档门禁测试（check_doc_refs / check_hardcode / doc_sync） |

> 相关：`MODEL_INDEX.md`（任务导航，逐知识单元的文档/实现/测试跳转）、
> `docs/README.md`（文档分层 + Doc:/Impl: 对齐约定）、`AGENTS.md`（硬约束 + 协作范式）。
