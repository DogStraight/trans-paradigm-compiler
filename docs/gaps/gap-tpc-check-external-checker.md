# Gap — tpc-check 外部 checker 插件协议（ROADMAP P2.6）

- 状态：未立项（backlog，非发布阻塞）
- 关联：ROADMAP P2.6（宽泛条目侧链接本文件）
- 参照：`docs/references.md`（Veryl/svlint 深调研 + 静态检查工具群段）、
  `docs/references.md`「静态检查器功能调研」（检查器功能矩阵 + 规则引擎架构）
- 前置：P1.9 稳定规则 ID + 机器可读输出（诊断模型）——**已满足**（
  `main.py::_cmd_check` 有 `--json` + 稳定诊断码 + suppress 注释；声明式规则表
  + `tests/policy/test_rule_coverage.py` 守可达性）。本档不受前置阻塞，属多周
  特性，留在 ROADMAP P2.6 未入队列

## 缺口是什么

tpc 目前的检查能力 = 自研（linter 语法层 + analyzer 语义层/声明式检查插件）。
缺一条**接入外部 checker**（官方/成熟检查工具，如 `veryl check`/verible/slang）
的通用协议——语言包 plugins/ 里声明"跑哪个外部 checker、怎么解析其输出"，
引擎只做通用执行器。自研检查覆盖不了成熟工具的语义级/规则级诊断（宽度/未
连接/风格等），"模型生成代码 → 检查闭环"想要 pylance 式体验就需外部工具
接入 + 输出归一。

## 为什么是缺口（影响面）

- 自研覆盖面有限：静态检查矩阵（references.md「静态检查器功能调研」）里 Verilator 的
  WIDTH/UNDRIVEN 类、Verible 的风格规则族、svlint 的 100+ 规则，tpc 全量
  自研不现实——外部工具接入是低成本补覆盖的路径。
- 每语言生态有"官方 checker"（Veryl 自带 `veryl check`），tpc 语言包若不能
  声明接入，用户要用就得自己绕管线。
- 场景盲区：格式化保真 / 变换等价 / 语法资产一致性——这些是**tpc 自管场景**，
  需要能对"官方 checker 认为合法"的结果做自己的断言（差分/幂等门禁式）。

## 成熟解法参照（见贤思齐）

- 🔥 **hdl_checker**（references.md 静态检查工具群段）："Repurposing existing
  HDL tools"——不自己解析，封装 pyGHDL/verible/slang 后端 → LSP Diagnostic。
  架构参照 = "检查服务 = 适配器"。⚠ 坑：后端输出格式版本耦合（verible 格式
  变化即坏）→ 声明层必须收口稳定接口（JSON + 稳定规则 ID）。
- 🔥 **svlint 深调研**（references.md）：规则四件套（check/name/hint/reason）、
  suppress 注释对（`/* svlint off rulename */`）、插件机制——外部规则的组织/
  豁免/扩展形态参照。
- 💡 **verible/slang/svlint JSON 输出实证**：三者均有机器可读输出（JSON/
  --diag-format）——归一化输入的可行性依据。
- 📌 **Veryl 触发**：本地镜像 `E:\research\veryl`，官方 `veryl check` 是首个
  验证目标（先做 veryl 本体验证，再推广 verible/slang）。

## 可实现性

- 方案形态：`grammar/<lang>/plugins/checker/tpc.toml` 两段声明——
  `[checker.external]`（命令 + 输出解析，JSON 输出/稳定规则 ID 收口，防版本
  耦合）与 `[checker.scenarios]`（tpc 自管场景：format_fidelity /
  transform_equivalence / 语法资产一致性）。
- 诊断归一化：外部 checker 输出（miette/JSON/文本）→ tpc 统一诊断模型。
- 依赖前置：P1.9 稳定规则 ID + JSON 输出（第一步纯增量、零外部依赖）。
- 验证路径：`grammar/veryl/plugins/checker/` 做 veryl 本体验证 → 再推广
  verible/slang。引擎只做通用场景执行器（延续"语言知识不进代码"）。

## 关联条目

- ROADMAP P2.6（本缺口，backlog；前置 P1.9 已满足）
- `docs/references.md`：Veryl / svlint / 静态检查工具群深调研（参照源）
- `docs/references.md`「静态检查器功能调研」：检查器功能矩阵 + 规则引擎架构
