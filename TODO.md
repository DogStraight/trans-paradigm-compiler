# TODO

> 排序原则（2026-08-11 重排，由"最大缺口"评估导出）：
> - **主线 = 第二语言（P0）**：验证"语言无关 / forkable"主张是否成立，是最大缺口；
>   同时带上**开发前置类工程化**（异常层级、调试基础设施）作为支撑。
> - **工程化拆两类**：开发前置类 → P0；发布收尾类（CI/安装/文档/覆盖率门禁）→ P2，不阻碍功能推进。
> - **零测试模块先补测试再堆功能**（预处理器 / formatter），避免在无测试地基上叠加。

## P0 — 第二语言验证（主线，最大缺口）

### P0.1 前置清理与支撑（工程化·开发前置）

> 现状：`pyproject.toml`（build-system/project/scripts/optional-deps/pytest/coverage）与 LICENSE 已落地；
> 2026-07-25 质量评估遗留 P0/P1（异常层级、覆盖率门禁）。

- [x] **异常层级统一**：统一异常体系 + 清理 except 吞噬 + TOML 模式验证（2026-07-25 P0 遗留）
      ——开发新语言前清理，避免新代码踩坑
      - core/errors.py：TransParadigmError 基类 + ConfigError/GrammarError/LexError/
        ParseError/TransformError/LintInternalError 子类；ParseError 迁移继承，core.define
        re-export 保持兼容
      - config 加载路径（define._load_tpc_meta / config_registry.load_all）→ ConfigError
      - 语法验证（rule_selector 产生式片段 / define peek / lookahead 入口规则）→ GrammarError；
        linter 配置缺失 → ConfigError
      - 清理 component/plugin loader 裸 except Exception: pass → OSError 收紧
- [x] **调试基础设施**（parser + linter 共用，当前最难调试的两个模块，第二语言开发会大量依赖）：
      a) 日志分级开关（LOG_TRACE/DEBUG/INFO/WARN/ERROR，`_log_level` 阈值替代空 lambda 替换，
         修复 `debug_log_file=None` 时 WARN 被吞——parser_core.py `_log_state`/`_log_level`）；
      b) parser 停点/trace（`set_trace(rule/token_pos)` + `_maybe_trace`，`try_rule_productions`
         入口按规则名/位置过滤，输出 token_pointer/当前 token/路径——parser_core.py + _production.py；
         原 `_failure_attempts` 已升级为失败现场 `_fail_sites`，见 failure-report）；
      c) discovery 节点树 token 区间 dump（`Discovery.dump_nodes`：rule + [start,end) →
         1-based/0-based 行号——linter/discovery.py）；
      d) 行号对账工具（`reconcile_line_numbers` / `reconcile_mismatches`——core/debug_report.py）

### P0.2 Tiny C 演示 DSL（第二语言本体）

> 依据 roadmap：语言范畴参照 c4（最小完备内核）+ chibicc（特性增量）；难度中等偏高（工作量型）。

- [ ] **范畴裁剪**：定三件事——①c4 内核 vs 扩展 ②任务拆分顺序（先哪层）③核心渗透预检
      （先跑最小 lexer 验证）
- [ ] **分层实现**：lexer → parser → analyzer → transform → renderer 逐层跑通（参照 chibicc 特性增量）
- [ ] **核心无渗透验收**：全程盯"分水岭"，任何 Verilog 知识进入 core 即暴露并回改
      （picorv32 修复记录证明核心改动均由 Verilog 缺口驱动，语言无关性从未被系统验证过）
- [ ] **模型可消费性演示 + walkthrough**：产出"从零搭语言"完整示例（原"自定义 DSL 完整示例"），
      兼外部贡献者上手参考——展示"语言知识全外部化"能力，降低拿本项目当骨架/改造的入门门槛
      （当前文档全围绕 Verilog，缺"从零搭语言"的 walkthrough）

### P0.3 渗透清理（第二语言暴露的残留渗透一并处理）

- [x] **boundary.py 语言渗透消除**：ScopeKind 从规则自身 `analyzer.scope.kind` 声明推导，
      boundary.py 不硬编码任何 keyword.* / 规则名 / 结构类别（遵守"不编码语言知识"铁律）
      - 为 BeginEnd/AlwaysStmt/InitialStmt/ForLoop/CaseStmt 补 `analyzer.scope` kind 声明
      - 只接受结构边界类别（ScopeKind 枚举内的 kind），类型系统 kind（如 TypeDecl 的 "type"）跳过
      - 附带修复：core/config_registry.py 插件 tpc.toml 的 bare data 声明缺失 bug
- [x] **其他暴露点清理**：第二语言验收中发现的 core/linter/transform 残留 Verilog 知识，
      记录并清理——grep 确认核心/linter/transform 源码无残留硬编码逻辑（仅注释示例）

## P1 — Verilog 实例完善（插件增强）

### P1.1 先补零测试的债

> 现状：预处理器与 formatter 均零单元测试（逻辑验证靠人工）。

- [ ] **预处理器单元测试**：指令原语/宏展开/ifdef 分支/逆向恢复（后续按部件分文件补充）
- [ ] **formatter 单元测试**：边界扫描器/分组/品类引擎/passes（后续按部件分文件补充）

### P1.2 预处理器增强

> 现状：已有 define/ifdef/include/undef primitives + `_expand.py`/`_reverse.py`；
> 已修复嵌套 ifdef inactive 祖先、续行拼接、include 配置化；
> 行首未知指令当前被 scan_directives 整体删除（跨子系统容错边界）。

- [ ] **管线内宏 token 决议**：行内宏调用在预处理器阶段展开/决议，管线内不再残留宏 token
      （linter P0 保险措施的前提；当前 e12 靠行内宏调用做 undefined-macro 可达性验证）
- [ ] **未知/错误指令容错**：行首未知指令从"整体删除"改为可配置策略 + 诊断报告（保留容错）
- [ ] **带参宏支持**（如 `` `define NAME(a,b) ... ``）：评估参数展开（当前仅文本替换）

### P1.3 格式化插件完善

> 现状：品类系统框架完成（boundary/engine/grouping/passes）；
> `formatter/tpc.toml` 品类配置仍为注释模板。

- [ ] **品类配置落地**：tpc.toml 启用实际品类（port_dir/declaration/parameter/assignment/
      genvar_integer/function/task + inst_port handler），替换注释模板
- [ ] **管线集成验证**：结构路径（Lex→边界扫描→引擎→输出）与主管线共存验证

### P1.4 增强语法渲染 + 管线展开开关

> 来源：2026-08-13 方向确认（formatter 完善过程中）——增强语法（typed_ports 等）解析展开后，
> 打印环节存在**格式化（保留增强语法源码）**与**展开（生成基础 Verilog）**两种需求；
> 现状只实现"展开"一路（transform 无条件 expand，renderer 从未渲染过增强节点）。

- [x] **现状确认**：typed_ports/tpc.toml 无 renderer 配置（`[lexer]/[grammar]/[analyzer]/[transform]`
      四个 section，缺 layout）；renderer 不认识 TypedPortDecl/TypeDecl 节点；管线仅
      `transform_enabled` 整体开关，无"展开 vs 保留增强语法"粒度；`TypedPortDecl.transform.kind="expand"`
      无条件执行
- [x] **增强节点 layout 规则**：给增强节点（TypedPortDecl/TypeDecl/TypeBody/TypeMember/TypeRole/
      TypeInvertPort/InvertDecl/TypedTypeSpec）写 TOML 布局规则（text/ref/join/line/indent DSL，
      与基础语法同机制）——renderer 布局驱动，零语言特定代码，增强节点直出
      - renderer 原语增强：join 新增 `no_soft` 选项（硬拼接不折行不 group，保留原始分隔符含空格）
        ——role 端口列表 `master : input clk, ...;` 需整行不折
      - 前置确认完成：TypedPortDecl parse 后 = type_spec(TypedTypeSpec) + instance_name(Declarator)；
        TypeDecl = type_name + body(TypeBody，members repeat 经 normalize 展平为 list)；
        normalizer 只消 optional/repeat/seq，增强节点保留
- [x] **管线展开开关（通用级）**：`expand_enhanced: bool`（默认 True）——False 时跳过
      analyze/transform（AST 保留增强节点，renderer 用增强 layout 渲染，format 照常）；
      True 走当前展开路径。判断依据 = 规则已有 `transform.kind`，不逐个组件加开关
      - 两条路最终都过 format（formatter 职责不变，纯排版）
- [x] **保留路径 formatter 适配**：formatter 从规则推导增强结构（不硬编码）——boundary 加
      curly 块支持（`{`/`}` 天然块边界，行尾 `{`=块入栈 / 行中 `{`=表达式计数排除），
      TypeBody/TypeImplDecl 缩进正确；format_output 默认 True 两条路都过 formatter
- [x] **TypeImplDecl / impl 绑定 layout**：TypeImplDecl（`impl [role] (ports) { body }`）、
      ImplBinding（`impl module [params] [inst] (ports);`）、ImplBindingWithInterface
      （`impl type.role [params] (ports) => iface;`）layout 已写（箭头 `=>`、括号手动给出）
- [ ] **验证补充**：typed_ports 更多样本（impl/nested/invert）在 expand_enhanced=True/False 两路
      均产出可读文本 + token 完整 + format 幂等（当前 5 单测覆盖 impl 绑定 + TypeImplDecl）

## P2 — 工程化收尾（发布准备，不阻碍功能推进）

### P2.0 机制可理解性（配置生命周期 + 表达式机制，第二语言过程暴露）

> 来源：c4 加入过程反思（2026-08-12）——`declare_cfg` 注册制配置的加载时序反直觉，
> 第二语言过程踩了 3 个修复（walkthrough #1/#2/#3）；表达式系统含多处隐式约定。
> 原则：先评估/文档化，太难理解则改机制。

- [ ] **配置生命周期评估 + 文档化**：declare_cfg（import 期注册）/ load_all（load 后推送）/
      load_language（替换全部声明）三阶段时序——模块变量 import 时是默认值、load 后才被推入，
      是"必须先 import 全部模块再 load_all""换语言后新 import 拿到旧默认值"等怪象的根源
      - 先评估机制简化（显式 config 对象注入 / 消除"import 期默认值"陷阱），给出成本-收益结论
      - 若保持注册制：写独立"配置生命周期"说明（时序图 + 多语言切换后果 + 常见坑），walkthrough 补一节
- [ ] **表达式系统隐式约定文档化**：Pratt + `is_atom` + `[[operator]]` 的隐式规则——
      operator 数组顺序 = 优先级低→高、atom 规则"长 production 优先"、三元 `arity=3`+`second`、
      一元与二元同符号靠 `position` 区分——walkthrough 补"隐式约定清单"节
- [ ] **组件协议文档**：插件层协议说明（`@register_plugin` / transform 钩子 / analyzer 原语 /
      setup_grammar 组件加载）——模型写插件（Python）靠它，避免从既有插件猜协议
- [ ] **c4 定位为最小语言包模板**：把 c4 正式作为"模型代写新语言"的起步模板
      （最小完整语言包 + 逐层指南），模型在其上做增量改造，而非从零生成
      （补强完成后"配置+插件"对模型从"能仿写"到"可代写"）

### P2.1 词法层数字形态配置化（NumberFSM 去硬编码）

> 来源：2026-08-12 盲区确认——数字字面量形态是语言知识（进制前缀/位宽语法/下划线/后缀/科学计数），
> 现在硬编码在 lexer/number_fsm.py（15 态全局单例 FSM），所有语言共享同一个"Verilog+C 混合"状态机。

- [ ] **数字形态配置化**：语言包声明数字形态（进制前缀、位宽 `N'b/h/d/o`、unsized `'d`、x/z/? 基值语义、
      下划线、小数/科学计数、后缀），替代硬编码 FSM
      - 现状：c4 解析 `0x1F` 是"碰巧兼容"（FSM 自带 C 前缀），非 c4 声明；`verify_verilog_range`
        也是 Verilog 特有——词法层最底层仍有语言渗透，与 P0.3 boundary 同族
      - 方案：数字形态声明 → 生成 FSM 或形态表（语言无关引擎 + 语言特定形态配置）
      - 前置：先补数字形态测试基线（现有 tests/lexer 覆盖不区分语言），再动 FSM
      - **形态模型对齐标准**：IEEE 1364-2005 A.8.7——统一骨架「形态 = `[size] base value`」，
        base = `'` + 可选 `s`(signed) + 进制字母(`d/b/o/h`)，value = 该进制 digit 集(含 `x/z/?`)，
        size 非零开头可选（unsized = size 空）；real_number 独立（`unsigned [. unsigned] exp [sign] unsigned`）。
        C 的 `0x`/浮点/科学计数 = 无 size 形态 + real 形态的子集变体，同一 schema 表达两族
      - **已知缺陷（重写 FSM 时一并修，当前不修）**：①signed base `'s` 缺失——`16'sd100` 被错切为
        `16`+`'`+`sd100`（AFTER_QUOTE 无 s 转移）；②`test_signed_literal` 断言空洞（只查 type 不断言
        content/token 数，假阳性掩盖①）；③`0'b1` 被接受（标准 size 必须 non_zero 开头）；④下划线行为
        已验证与标准一致（`1__2`/`_1`/`1_` 正确拒绝），无需处理
      - **测试基线要求**：按语言固化**完整 token 序列 + content**（不只类型），signed 位宽用例必须含断言

> 现状：`.github/` 为空目录、全库无 `ci.yml`（CI 曾存在后被 `38e2daf` 移除）；缺 CONTRIBUTING/CHANGELOG/API 文档；
> 建议在第二语言期间同步建立覆盖率基线，防止渗透回归。

- [ ] **覆盖率门禁**：恢复覆盖率测量脚本 + 目标 ≥90%（2026-07-25 P1 遗留）
- [ ] **恢复 CI**：`.github/workflows/ci.yml`（Windows + Python 3.11/3.12/3.13 矩阵，pytest + coverage）；
      前置：从 `.gitignore` 移除 `.github/`（当前规则导致 CI 无法被追踪）
- [ ] **安装可验证**：`pip install -e ".[test]"` 通过（pyproject 已建未验证，依赖管理评估遗留）
- [ ] **补文档**：CONTRIBUTING、CHANGELOG、API 文档（docs/ 现有 12 文件缺这三项）

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
