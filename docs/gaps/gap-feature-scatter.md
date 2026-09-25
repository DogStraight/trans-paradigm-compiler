# Gap — 功能散点（一处功能、N 处登记）与上游契约耦合

- 状态：未闭环（**方案未定案**；0.1.3 立项，先立档后动手）
- 关联：`TODO.md`「0.1.3 立项」WS2；`docs/engine_overview.md`「横切机制」；
  `core/component_protocol.md`（组件协议）、`core/config_lifecycle.md`（配置生命周期）、
  `core/engine_compat.py`（引擎 API 兼容校验）、`policy/structural_budget.md`（欠账口径）
- 参照：`docs/references.md`（GCC 路线 / MLIR ODS 生成器 / 各 lint 插件形态）

## 边界是什么（三个不同的痛点，机制不同，不可混为一谈）

### P-A 登记散点：一个功能要碰 N 个地方

实测（2026-09-25，`git show --stat` + 全库 `Select-String -List` 计数）：

| 观测 | 实测 |
|---|---|
| 一条**已存在**诊断码散落的文件数 | `W105` = **20** 个文件；`MH001` = **8**；`TP003` = **4** |
| 加一条**规则族**（AW001/AW002） | **6** 个文件，其中**含引擎侧** `analyzer/checks.py` |
| 加一条**规则组**（NC014-016 前后缀） | 5 个文件（插件内 2 + 测试 1 + TODO/references）——**未动引擎** |
| 加一个**检查插件**（hier_check） | 4 个文件（插件 2 + 测试 1 + 一处既有插件微调）——**未动引擎** |
| 规模现状 | 25 个插件 `tpc.toml`，共出现 **28 种段名**（`[analyzer]`/`[grammar]`/`[lexer]`/`[capabilities]`/`[[pipeline.units]]`/`[[formatter.categories]]`/…） |

散落面的构成（同一个功能，被**多个互不知晓的观测点**分别要求登记）：

1. **插件内**：`tpc.toml`（段声明）+ 实现 `.py` + 规则表 `.toml`（如 `rules/always.toml`）
2. **引擎侧登记表**：`core/_protocol.py` 的契约键常量（24 条）、`declare_cfg` 配置段
   （18 处调用，**几何全部在引擎模块内，grammar 侧 0 处**）、`tools/config_sites.py` 的
   引擎词汇白名单（`_VOCAB_DISPATCH` / `_VOCAB_ELEMENT` / `_VOCAB_SECTION`）
3. **行为基线**：`tests/e2e/samples/*/expected.json`、`tests/e2e/samples/real/diag_baseline.json`、
   `tools/min_pack_baseline.json`、`tests/e2e/mutation/injectors.py`、`tests/e2e/run_all_tests.py`
4. **文档治理**：插件 README、`linter/linter_architecture.md`、`MODEL_INDEX.md`、CHANGELOG
   （`tests/policy/test_doc_stats.py` 会把它们变成门禁）

判据：**同一事实被写在 ≥2 个必须手工保持同步的位置**（不是"文件多"本身——测试与文档
本来就该有；问题是**没有单一事实源**，靠人记着同步）。

### P-B 上游契约耦合：引擎一变，语言包被迫跟着改

实测（ADR-0019 精化基座重构全程，`d20938c^..HEAD`，26 提交）：

| 区域 | 被迫改动文件数 |
|---|---|
| `grammar/`（语言包侧） | **11** |
| `tests/` | **11** |
| `analyzer/`（引擎侧） | 10 |

即：**一次引擎边界调整 → 语言包侧 11 个文件 + 测试侧 11 个文件跟着改**。这次改动本身
是值得的（删掉约 1000 行引擎侧语言知识），但**代价被记在了语言包账上**，而语言包是
tpc 对外的"资产范围"——这个代价会随语言包数量线性放大（C 包、SV 包、用户标定包）。

### P-C 兼容只剩一个粗粒度开关

现役机制 `[engine] api = "0.1"`（`core/engine_compat.py`）：**整条 API 线**的
major.minor，不区分"该包到底用了哪些引擎能力"。后果：

- 引擎 minor 一动，**所有**包都拒绝加载（内置三包 `c4` / `verilog` / `yaml` 都只声明 `"0.1"`）；
- 无法表达"这个包只用语法声明，没碰 elaboration，所以精化协议改了不影响它"；
- 报错只能说"包与引擎不兼容"，说不出**缺哪一项能力**；
- 用户侧只剩两条路：升级包 / 换引擎——没有"能力协商 + 精确缺项"的中间态。

## 成熟解法参照（💡 启发，采用前须逐条核验）

> 纪律：外部事实落 `docs/references.md` 后再引用；以下为**路线候选**，未做逐条核验。

- 💡 **能力协商（capability negotiation）**：客户端/服务端各自广播"我支持哪些能力 +
  版本"，按交集工作（LSP `initialize` / `ServerCapabilities` 是典型形态）。对应 P-C：
  包声明 `uses = [...]`，引擎内置能力版本表，不匹配时**精确报缺哪一项**。
- 💡 **单一贡献点清单（contribution points）**：编辑器插件把"我贡献了什么"全写在
  **一个 manifest** 里（命令/菜单/语言/配置 schema），宿主从 manifest 派生 UI、配置
  schema 与默认值，插件不再分别登记。对应 P-A：功能 = 清单里的一项，其余**派生或校验**。
- 💡 **配置/代码生成器**：`references.md` 已记 GCC 机器描述的 `genrecog`/`genoutput`/
  `genattrtab` 与 MLIR ODS（`.td` → 生成构造器/验证器）——**配置面本身要配工具链**，
  否则就是纯负担。对应 P-A：`tools/config_sites.py` 已是雏形（读声明 → 校验词汇），
  可扩为"读清单 → 校验/派生全部登记点"。
- 💡 **特性开关 + 版本线**（feature flags / edition / MSRV）：Rust 用 `edition` 表达
  "同一编译器下的语言版本"，用 feature 表达"增量能力"；这与 ROADMAP 已定调的
  C「标准插件族」（核心基线 + `requires` 链）同构——**语言包侧这道已经想清楚了**，
  缺的是**引擎侧**对"包用了哪些能力"的对称表达。
- 📌 **不做**：给每个功能发明一套新的 DSL / 生成器框架——配置面膨胀风险已在
  `references.md`（数字形态 7 字段 × 4 形态块的实证）付过学费；本议题只做
  **"把已有登记点收敛成一处"** 与 **"把已声明的事实拿去校验"**，不新增表达语言。

## 可实现性（拆步，每步可独立验证，先度量后收敛）

- **步 1 度量（零风险、不发明机制）**：`tools/feature_sites.py`——按**功能分族**
  （加语法构造 / 加检查规则 / 加能力位 / 加渲染规则 / 加配置键）输出"接触点清单"，
  并建立**接触点预算**基线。判据沿用 `policy/structural_budget.md` 的哲学：
  **度量的是"未处置的欠账"**——逐项下结论（该合并 / 该接受）后从预算里出去，
  而不是禁止文件数多。验证：工具输出 + 一个门禁测试（超预算即失败，登记表可审计）。
- **步 2 试点收敛（选一族做单一注册点）**：建议**检查规则族**——它已有
  `rules/*.toml` 声明面雏形，且实测散落最重（一条码最多 20 文件）。目标判据：
  加一条规则 = 改**清单 1 项 + 实现 1 文件 + 测试 1 文件**，其余（诊断码表、词汇白名单、
  基线登记、文档索引）**由工具校验或派生**。验证：拿一条真实新规则走一遍，统计接触点
  下降数（对照步 1 基线）。
- **步 3 契约协商（P-C）**：`[engine].api` → 能力清单（`uses = ["grammar.inject.v1",
  "capability.elaborator.v1", …]`）+ 引擎内置能力版本表 + 精确缺项报错；未声明能力的
  包不受无关能力演进影响。按"不留向后兼容"：切换后**删掉**旧 `api` 线，不留双路径
  （升级期若必须并存，须写明删除期限与判据）。验证：三个内置包各自声明 + 造一个
  "只声明子集"的包证明无关演进不误伤 + 缺项报错文案含具体能力名。

## 步 1 实测结果（2026-09-25，`tools/feature_sites.py --save` 基线）

| 功能族 | 实例 | 散点合计 | 中位 | 最大 | 结论 |
|---|---|---|---|---|---|
| `check` 加检查规则 | 24 | **56** | 2 | 5 | 散点**高度重复**：几乎每条规则都要在同样 5–6 个文件登记 |
| `syntax` 加语法构造 | 7 | **0** | 0 | 0 | 无跨文件登记点（插件自动发现）→ 该族问题只在**跨阶段文件数**：一个构造 2–11 个文件（`sim` = 11） |
| `capability` 加能力位 | 3 | **30** | 9 | 15 | 散点最贵的一族（`formatter` 15 / `macro_policy` 9 / `elaborator` 6） |
| `config` 加配置段键 | 14 | **26** | 2 | 3 | 中等 |

**步 2 的收敛目标（由数字定，不靠直觉）**：`check` 族的散点集合是**同一批文件反复出现**——

    core/check_registry.py                  （规则注册表，唯一合理的单一来源候选）
    tests/e2e/mutation/injectors.py          （变异注入器的码清单）
    tests/e2e/samples/check_accuracy/expected.json
    tests/e2e/samples/real/diag_baseline.json
    tests/e2e/eval_check_accuracy.py / eval_benchmark.py（评分脚本的码枚举）
    analyzer/semantic_checks.md              （文档侧码表）

即"一条规则码要手写进 6 处"。步 2 判据：**由 `check_registry` 单一来源派生或校验其余
各处**（能派生就派生、不能派生就让门禁比对），目标"加一条规则 = 清单 1 项 + 实现 1 文件 +
测试 1 文件"。`capability` 族（30 散点）是第二个候选目标。

## 步 2 结果（2026-09-25）：机器可读登记点已收敛

**做法**：码的单一来源 = 声明式规则表 ∪ 插件 handler `code=` 字面量，抽成**一份共用实现**
`tests/_rule_codes.py`（`test_rule_coverage.py` 与新增门禁共用——两处各自实现提取逻辑
本身就是新的散点）。新增 `tests/policy/test_code_registry_sync.py` 把机器可读登记点接上校验。

**门禁有效性（实测，非声明）**：注入假码 `ZZ999` 到变异注入器 → 该门禁 **1 failed**、
还原后 **0**；三处检查实际校验 **11 / 13 / 7** 条码（非空转）。
⚠ 过程中复现了同一坑两次：码形态正则写成 `[A-Z]{2,4}` 会把**单字母前缀码**
（`W101/W201/W202` 等 8 个）静默漏出校验面——两处都显式记进注释。

**收敛账（`tools/feature_sites_converged.json`，须 reason + source 指向门禁）**：

| 登记点 | 收敛方式 |
|---|---|
| `tests/e2e/mutation/injectors.py` | 门禁校验 target/allowed_extra 必须已定义（否则变异静默失效） |
| `tests/e2e/eval_benchmark.py` | 门禁校验映射值必须已定义（否则评分少算一类） |
| `tests/e2e/samples/real/diag_baseline.json` | 门禁校验计数键必须已定义（码删则残留键暴露） |
| `tests/e2e/samples/check_accuracy/expected.json` | 既有门禁双向核对（已定义未入样本即失败） |

**预算变化**：`check` 族 **56 → 16**（中位 2→1、最大 5→3），其余三族不变。

**剩余 16 点（步 2b 候选，未见底就别报收敛）**：

    6  analyzer/semantic_checks.md          机制文档的码表（散文/成范围出现，逐 token 校验会误报）
    5  tests/e2e/eval_check_accuracy.py     仅 docstring 里枚举码（可改为不枚举 → 真删除）
    2  tests/_check_test.py                 共用测试助手（若为迭代用，应改读单一来源）
    1  core/check_registry.py               规则表模块头 docstring 的示例码（文档，非登记）
    1  tools/check_gate_efficacy.py         变异目标（与注入器同理，可接同一门禁）
    1  analyzer/suppress.py                 抑制逻辑引用码（合理引用）

**接受的边界（有意不收敛）**：散文类（机制文档码表、docstring 枚举）**不**接逐 token
校验——会成范围（`NC001-NC010`）与历史提及出现，逐 token 校验是误报机器；
这类由 `test_doc_stats.py` + 人工复核承担。判断标准始终是"**是否必须靠人记着同步**"，
不是"文件里有没有出现这个码"。

## 关联条目

- `TODO.md`「0.1.3 立项」WS2（执行步骤与待决策点）
- `docs/engine_overview.md`「横切机制」（现役机制清单：配置注册制 / 组件协议 / 核心类型 /
  token 协议）——本档讨论的是**这些机制之间的重复登记**，不推翻它们
- `core/engine_compat.py`（P-C 的现状实现）、`core/config_registry.py`（配置段登记面）
- `policy/structural_budget.md` + `tools/structural_kept.json`（欠账口径与登记表的先例）
- `tools/config_sites.py`（配置同步点位工具的现役形态）
