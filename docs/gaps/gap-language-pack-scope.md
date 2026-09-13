# Gap — 语言包范围与 yaml 边界（规模 / SV / 插件划分 / 增强语法）

- 状态：范围声明（刻意选择）
- 关联：ROADMAP「SystemVerilog 语言包」；`grammar/yaml/`
- 参照：Language server/编译器前端对大型语法的工程组织（Clang 分层）

## 边界是什么

1. **中小语言**（接受）：配置驱动语法是 DSL/子集/自定义扩展的最佳点（c4、
   Verilog 核心）。C++ 规模语法墙不是上下文敏感（解析器经符号表解决
   `a*b` 声明 vs 乘法）——墙是**规则规模与语义深度**（数百 production/模板
   实例化/重载/复杂类型），TOML 配置无法压缩、也不是本工具目标。大语言推荐
   做**精选子集**（Verilog 包本身就是可综合子集，仿真构造移插件）。
2. **配置有学习曲线**（接受）：语法包横跨五类配置面（语法 production/节点
   `$N` 绑定/analyzer 钩子/transform 输出/renderer layout），各有隐式约定。
   二次开发入口：`docs/MODEL_INDEX.md` + `core/component_protocol.md`。
3. **非行为验证器**（接受）：校验良构（语法/结构/命名/跨模块一致），不仿真/
   不综合，不判断硬件正确性——前端/规范执行工具，非正确性证明器。
4. **无 SystemVerilog**（backlog）：包目标 Verilog-2005；SV 构造
   （interface/class/always_ff/assertion/package/UVM）不在当前范围。加 SV =
   **core + plugin 增量**路线项（ROADMAP「SystemVerilog 语言包」），非引擎改动。
5. **Verilog-2005 标准面已齐；可综合核心 vs 仿真/库插件**（接受 + 余量跟踪）：
   主包覆盖可综合子集；仿真/库语法在插件（gates 26/UDP/specify/config/
   defparam/过程 assign/NetTypes）。剩余余量（darkriscv 嵌套条件编译位置精度等）
   与 references.md 跟踪。
6. **yaml 缩进推断锁**（接受 + 摩擦）：`[indent] level="auto"` 首结构行锁定
   单位；混单位文件锁定后错解析；渲染器经 AST-root `_indent_unit` 戳重缩进到
   锁定单位——块标量逐字内容仅在源单单位时保持对齐。
7. **yaml plain 标量配置宽松近似**（摩擦）：`[plain]` 模式（字符类 +
   `stop_space_after`/`no_space_after_tokens`/`flow_terminators`）覆盖真实
   配置值形态（`${{}}`/URL/多词/CJK/词内 `,{}[]`）——偏离 YAML 1.2 严格
   plain 规则。剩余 gap：数字引导多点多值（`1.2.3` 拆分，number 分支赢）、
   无 tab 分隔词、值不跨行、带转义引号不支持。
8. **增强语法 linted 非豁免**（事实）：前置 linter 共享 parser 规则表（含插件
   语法），合法 `type`/`type.role`/`impl` 构造过 lint 门禁；`no_lint=True`
   是逃生门但不需要。

## 为什么是范围（影响面）

1/3/4/5 是产品定位（面向可配置规范执行的 DSL/子集工具），做大语言/SV/仿真是
路线项非缺陷；yaml 6/7 是 yaml 包以"配置宽松"换"覆盖真实值形态"的取舍；
8 澄清增强语法不需逃生门（防误导）。

## 成熟解法参照（见贤思齐）

- SV/大语言支持：Clang 式分层（core 语法 + 插件增量）是 ROADMAP 方向，不重新
  发明单体内核。
- yaml plain 严格性：YAML 1.2 规范是裁判；tpc 取"配置宽松"实为覆盖真实配置
  形态的工程取舍（见 `grammar/yaml/` 现有注释）。

## 可实现性

- 4：ROADMAP「SystemVerilog 语言包」（远期 backlog）——core+plugin 增量路径。
- 5：剩余余量（语法/位置精度）按需处理。
- 6/7：yaml 包专项（如需）：7 的 `1.2.3` 拆分需 plain 分支优先级重排（number
  vs plain 消歧）；6 的混单位是捕获层约定，改动需 yaml 语料门禁。
- 1/2/3/8：不改（范围/文档事实）。

## 关联条目

- ROADMAP「SystemVerilog 语言包（远期 backlog）」
- `grammar/yaml/`（6/7 的消费方）
