# 静态检查器功能调研（Verilog/HDL + 可定制规则引擎）

> 性质：设计来源记录（references）。是 `decisions/0004-semantic-check-slot.md` 的前置调研，
> 决定 tpc 语义检查系统"做什么（功能矩阵）"与"怎么学（规则架构）"。
> 日期：2026-08-22。规则引擎部分经 web 检索核实，来源 URL 附各节末。

## 一、Verilog/HDL 静态检查器功能矩阵

| 类别 | Verilator | Verible | SVLint | Slang/iverilog | SpyGlass/Questa |
|---|---|---|---|---|---|
| 宽度/截断/扩展 | ✅ WIDTH（elaboration 后按具体参数值查） | ❌ | ⚠️ 部分 | ⚠️ 诊断级 | ✅ 全套 |
| 未连接信号 | ✅ UNDRIVEN | ❌ | ❌ | ❌ | ✅ |
| 未使用信号 | ✅ UNUSED/UNUSEDSIGNAL | ❌ | ❌ | ❌ | ✅ |
| 推断锁存器/组合环 | ✅ LATCH/UNOPTFLAT | ❌ | ❌ | ❌ | ✅ |
| case 完整性 | ✅ CASEINCOMPLETE/CASEOVERLAP | ❌ | ❌ | ❌ | ✅ |
| 隐式声明 | ✅ IMPLICIT | ❌ | ⚠️ | ⚠️ | ✅ |
| 命名/风格 | ⚠️ 少量 | ✅ 主场（module-filenames、line-length、no-tabs、always-comb/ff 等） | ⚠️ | ❌ | ⚠️ |
| CDC/跨时钟 | ❌ | ❌ | ❌ | ❌ | ✅ 主场 |
| 复位/DFT/功耗 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 可综合性 | ⚠️ 部分 | ❌ | ❌ | ❌ | ✅ |
| **配置化参数敏感性** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **链级溯源报告** | ❌ 单点 | ❌ | ❌ | ❌ | ⚠️ 层级化，不跨语句链 |

### 各工具要点

- **Verilator**（开源，lint 最接近"真静态检查"）：`--lint-only`；W 系列警告按类别前缀（WIDTH/UNDRIVEN/UNUSED/UNOPTFLAT/IMPLICIT/MULTIDRIVEN/VARHIDDEN/BLKSEQ/CASEINCOMPLETE/CASEOVERLAP/LATCH/LITENDIAN/PINCONNECTEMPTY 等）。
  配置/抑制：代码内 `/* verilator lint_off WIDTH */` + CLI `--Wno-X`/`--Werror-X`；severity 由用户映射到 error/warning。
  **关键**：宽度检查发生在 elaboration 之后，拿**具体参数值**查截断——`DATA_W=16` 时 `16'hFFFF` 合法；`DATA_W` 改 8 才报。
  它结构上无法知道"配置可能变"（没有配置敏感性的概念）。
- **Verible**（开源，风格/结构规则主场）：`verible-verilog-lint`；规则如 module-filenames、line-length、no-tabs、always-comb/ff、generate-label、forbidden macros。
  配置：`.rules.verible_lint` YAML（rule → {enabled, options}）；抑制：`// verilog_lint: waive rule-name`。
- **SVLint**（开源，语法/结构为主）：`.svlint.toml` 配置（OpenTitan/ibex 实例），语义检查弱。
- **Slang / Icarus**：编译器前端诊断 + elaboration 期宽度告警，非独立 lint 系统。
- **SpyGlass / Questa lint**（商业，功能天花板）：Lint/CDC/RDC/Reset/DFT/power/constraints/assertions 全套类别、数千条规则、waive 机制、层级化报告；无跨语句链溯源。

### 来源

- [Verilator 文档（warnings/lint 说明）](https://opensecura.googlesource.com/3p/verilator/verilator/+/cdeb6e792f4beb1faa96523b6f37f69d23b5e4fd/docs/guide/exe_verilator.rst)
- [Verible verilog-lint](https://chipsalliance.github.io/verible/verilog_lint.html)、[Verible 规则源码 default_rules.h](https://github.com/chipsalliance/verible/blob/4f98e1456daaac3b268544aff39879c05f37a7be/verilog/analysis/default_rules.h)
- [SVLint crate 文档](https://docs.rs/crate/svlint/0.4.14)、[OpenTitan .svlint.toml 实例](https://opensecura.googlesource.com/3p/lowrisc/opentitan/+/d8dca9f9bbad1bda2a238bff3bf4bd1f7133d332/.svlint.toml)
- [VC SpyGlass CDC 数据手册](http://www.beintech.com.cn/template/default/pdf/vc-spyglass-cdc-ds.pdf)、[VC SpyGlass RDC 数据手册](https://www.synopsys.com/content/dam/synopsys/verification/datasheets/vc-spyglass-rdc-ds.pdf)

## 二、可定制规则引擎架构对比（Semgrep / CodeQL / ESLint / clang-tidy / Ruff）

> 调研目标：tpc 要"规则=配置/数据、复杂检查=脚本"——业界五个代表性系统怎么设计。

### 1. Semgrep — 纯声明式 YAML 规则引擎

- **声明方式**：纯配置（YAML）。顶层 `rules:` 列表，每条规则含 `id`/`message`/`severity`/`languages`/匹配逻辑（`pattern` 或 `patterns` 组合）。不支持用户脚本——复杂逻辑靠声明式算子组合。
- **Schema 字段**：`id`、`message`（`$VAR` 元变量插值）、`severity`（ERROR/WARNING/INFO）、`languages`、`patterns`/`pattern`、`fix`（自动修复模板）、`metadata`（cwe/owasp/confidence/category 等）、`paths`（include/exclude）、`mode`（search/taint/join）。
- **匹配表达**：AST 模式匹配——规则里写目标语言代码片段（`exec($CODE)`），引擎解析成 AST 做结构等价匹配。元变量 `$X`（单个 AST 子树）、`$...ARGS`（任意多个 token）、省略号 `...`；布尔算子 `pattern-either`/`pattern-inside`/`pattern-not`/`pattern-not-inside`/`pattern-regex`；元变量约束 `metavariable-regex`/`-pattern`/`-comparison`；`mode: taint` 声明 `pattern-sources/sinks/sanitizers` 做数据流分析（Pro 版给数据流路径链）。
- **抑制**：`// nosemgrep`（本行）、`// nosemgrep: rule-id`、文件级首行 `# nosemgrep`、`paths.exclude`、不选即关。
- **扩展性**：Semgrep Registry——规则就是 YAML 文件，按类别组织成规则包（packs），`--config p/security-audit` 拉取；本地 YAML/git 仓库均可作 `--config`。
- **测试**：`semgrep test` 内置——夹具文件内 `// ruleid: <id>`（必须命中）/ `// ok: <id>`（不得命中）注释驱动断言，零代码。
- **报告**：文件路径 + 行/列 + 命中片段 + 插值 message + severity；`--json`/SARIF；`--autofix` 应用 fix。

### 2. CodeQL — 声明式逻辑查询语言（数据流/溯源天花板）

- **声明方式**：写代码（QL 声明式查询语言，类 Datalog+OO）。`.ql` 文件即规则：`from 变量 where 谓词 select 结果`，直接查询从源码编译的关系数据库（AST/符号表/CFG/数据流图/SSA）。
- **Schema 字段**：元数据写在查询注释头——`@id`/`@name`/`@description`/`@kind`（problem/path-problem/alert）/`@severity`/`@precision`/`@tags`/`@sub-severity`；结果契约由 `select` 定义（path-problem 多 source/sink 两列，报告器据此画数据流路径）。
- **匹配表达**：谓词/量词/递归查询库实体（Function/Expr/Call 等）；数据流继承 `TaintTracking::Configuration` 覆写 `isSource`/`isSink`/`isSanitizer`/`isAdditionalTaintStep`，库自动完成跨过程、跨文件路径计算。
- **抑制**：查询套件选择（不运行即不报）；GitHub Code Scanning inline `// codeql[<query-id>]`；SARIF suppression。
- **扩展性**：QL packs（`qlpack.yml`）发布到 GHCR；`.qls` 查询套件按场景分组。
- **测试**：`codeql test run` 对比 `.expected` 期望快照。
- **报告**：SARIF；**path-problem 输出 source→中间步→sink 完整路径**——五者中溯源能力最强。

### 3. ESLint — 规则即 JS 代码（visitor + 数据配置的双层模型）

- **声明方式**：双层——规则 = JS 代码（模块导出 `meta` + `create(context)` 返回 AST visitor）；配置 = 数据（`rules: { "id": ["error", options] }`）。
- **Schema 字段（meta）**：`type`（problem/suggestion/layout）、`docs`（description/url/recommended）、`schema`（JSON Schema 校验 options，fail-fast）、`messages`（消息模板字典 `{{placeholder}}`，用 messageId+data 插值，i18n 友好）、`fixable`、`hasSuggestions`、`deprecated`、`defaultOptions`。严重度不在规则里而在配置中（off/warn/error）。
- **匹配表达**：AST visitor + esquery 选择器 + scope/类型 API（getScope/getAncestors/context.options/sourceCode）。
- **抑制**：`/* eslint-disable */`、`eslint-disable-line`、`eslint-disable-next-line`、`eslint-enable`、文件内配置注释、overrides/ignorePatterns。
- **扩展性**：npm 插件包 `eslint-plugin-*`（rules/configs/processors），flat config 注册。
- **测试**：**RuleTester**——`run(name, rule, { valid: [{code}], invalid: [{code, errors: [{messageId, type, line, column, data, suggestions, output}]}] })`，逐字段断言，事实标准。
- **报告**：`context.report({ node, loc, messageId/message, data, fix, suggest })`；无内置数据流，规则可自研跨函数分析。

### 4. clang-tidy — 规则=编译器内 C++ 代码，配置=YAML 文件

- **声明方式**：check 本体是 C++ 代码（编译进二进制，用户一般不现场写）；用户声明在 `.clang-tidy` YAML（`Checks: '-*,bugprone-*'` + CLI）。
- **Schema 字段**：命名空间前缀即分类（bugprone-/readability-/cppcoreguidelines-/modernize-/performance-/misc-/cert-/hicpp- 等）；`.clang-tidy` 键 `Checks`/`WarningsAsErrors`/`HeaderFilterRegex`/`CheckOptions`（每个 check 的参数表）；严重度由 check 决定。
- **匹配表达**：C++ AST matcher（`callExpr(callee(functionDecl(hasName("strcpy"))))`）+ check 回调里写语义判断；部分正则选项（如 identifier-naming 风格）。
- **抑制**：`// NOLINT`、`// NOLINT(check-name)`、`// NOLINTNEXTLINE`、`// NOLINTBEGIN...NOLINTEND`（区间）、`-checks=`/`-line-filter=`。
- **扩展性**：无市场；自定义 check 走 `ClangTidyModuleRegistry`，贡献上游或自建二进制。
- **测试**：lit 测试，文件内 `// CHECK-NOTES:`/`// CHECK-MESSAGES: [[@LINE-x]]`/`// CHECK-FIXES:` 期望注释。
- **报告**：clang 标准诊断格式 + notes + fix-it；单翻译单元，无跨过程数据流路径。

### 5. Ruff — 配置驱动的内置规则 + Rust 插件生态（对比参考）

- **声明方式**：纯配置（TOML）启用，规则本体 Rust 代码编译进二进制。
- **Schema 字段**：规则有 code（F401）/name/category/fixable/preview；配置 `lint.select`/`ignore`/`extend-select`/`per-file-ignores`（glob → 规则列表）/`exclude`/选项表。
- **抑制**：`# noqa`、`# noqa: F401`、`# ruff: noqa`（文件级）、`per-file-ignores`。
- **扩展性**：Rust 插件 API（0.9+，`ruff plugin`），生态早期。
- **测试**：insta snapshot 快照（用户侧无测试框架）。
- **报告**：诊断 code+位置，`--fix`；无数据流，定位快速 lint。

### 对比表

| 维度 | Semgrep | CodeQL | ESLint | clang-tidy | Ruff |
|---|---|---|---|---|---|
| 声明方式 | 纯配置 YAML | 声明式查询语言 QL | 双层：规则=JS，配置=数据 | 规则=C++ 编译期，启用=配置 | 规则=Rust 编译期，启用=TOML |
| Schema 字段 | id/message($VAR)/severity/patterns/fix/metadata | 注释元数据 @id/@kind/@severity + select 契约 | meta.type/schema/messages({{x}})/fixable + 配置 off/warn/error | 命名空间前缀=分类 + CheckOptions + WarningsAsErrors | code/name/category/fixable + select/ignore/per-file-ignores |
| 匹配表达 | AST 模式 + metavariable + 布尔算子 + taint mode | QL 谓词/量词/递归 + TaintTracking::Configuration | JS visitor + esquery + scope/类型 API | C++ AST matcher + 正则选项 | Rust AST 遍历（内部 DSL） |
| 抑制 | nosemgrep[:id] + paths.exclude | 套件选择 + codeql[id] + SARIF suppression | eslint-disable[-line/-next-line] + overrides | NOLINT[:check]/NEXT/BEGIN-END + -checks= | noqa[:codes] + per-file-ignores |
| 扩展性 | Registry + 规则包（YAML 分发） | QL packs + .qls 套件 | npm 插件包 | 上游贡献/自建二进制 | Rust 插件 API（早期） |
| 测试 | ruleid:/ok: 注释驱动 | .expected 快照 | RuleTester valid/invalid 断言 | lit CHECK-NOTES/MESSAGES | insta snapshot |
| 报告/溯源 | 位置+片段+fix；taint 跨过程，Pro 给路径 | SARIF；path-problem source→sink 完整路径 | 位置+模板+fix/suggest；无内置数据流 | 位置+notes+fix-it；无数据流 | 位置+fix；无数据流 |

## 三、共识总结与对 tpc 的启示

### 业界共识（五工具交叉验证）

1. **规则元数据永远是数据**（id/category/severity/message 模板）；匹配逻辑可以是数据（Semgrep）或代码（ESLint）——"分界线"是设计选择。
2. **统一抑制语法与规则分层正交**：五工具全部支持"inline 注释 + 可选规则 id + 文件级 + 配置排除 + per-rule 关闭"，数据规则与脚本规则共用同一套。
3. **数据流能力应是引擎的，规则只描述端点**（CodeQL TaintTracking、Semgrep taint mode）：声明 sources/sinks/sanitizers，复杂条件开放脚本钩子。
4. **按层提供测试**：声明层用注释驱动测试（ruleid:/ok:，零成本）；脚本层用断言式（RuleTester）。
5. **修复能力也分层**：声明式 fix 模板（Semgrep `fix`）+ 脚本式 fix 回调（ESLint `fix`/`suggest`），共用同一 autofix 管道。

### 对 tpc 的启示（落地到语义检查插槽）

- **双层模型**：L1 声明层（TOML 规则=数据，Semgrep schema 骨架：id/message 模板/severity/匹配描述/metadata）+ L2 脚本层（`@register` 原语 / handler 模块，ESLint visitor 模型）。两层共享同一报告管道（消息模板/severity/位置/链）。
- **链级溯源是空白也是机会**：HDL 领域无任何工具做跨语句链溯源；CodeQL path-problem 证明其价值——tpc 在 analyzer 符号表之上做"先收集、后走查"的 post-pass 是自然路径。
- **配置敏感性是 tpc 独有差异化**：Verilator 在 elaboration 后按具体参数值检查，结构上不可能知道"配置可能变"；tpc 的配置体系就在自己身上，能查"字面量 vs 符号宽度"这类配置脆弱性。
- **范围纪律**：宽度截断/未连接/未使用/锁存器等 Verilator 已覆盖的检查不重造；tpc 只做 ① 配置敏感类检查（唯一性）+ ② 链级溯源（稀缺性）+ ③ 声明式规则机制（通用性）。
