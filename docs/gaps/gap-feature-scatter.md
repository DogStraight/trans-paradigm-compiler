# Gap — 功能散点（一处功能、N 处登记）与上游契约耦合

- 状态：**已定案（机制现役）**——判据与工具见 `tools/feature_sites.py`（接触点计量 + 预算），
  契约协商见 `core/engine_capabilities.py` / `core/engine_compat.py`
- 关联：`docs/engine_overview.md`「横切机制」；`core/component_protocol.md`（组件协议）、
  `core/config_lifecycle.md`（配置生命周期）、`policy/structural_budget.md`（欠账口径）
- 参照：`docs/references.md`（GCC 机器描述 / MLIR ODS 生成器 / 各 lint 插件形态）

## 边界是什么（三个不同的痛点，机制不同，不可混为一谈）

### P-A 登记散点：一个功能要碰 N 个地方

实测（2026-09-25，`git show --stat` + 全库计数）：

| 观测 | 实测 |
|---|---|
| 一条**已存在**诊断码散落的文件数 | `W105` = **20** 个文件；`MH001` = **8**；`TP003` = **4** |
| 加一条**规则族**（AW001/AW002） | **6** 个文件，其中**含引擎侧** `analyzer/checks.py` |
| 加一条**规则组**（NC014-016 前后缀） | 5 个文件（插件内 2 + 测试 1 + TODO/references）——**未动引擎** |
| 加一个**检查插件**（hier_check） | 4 个文件（插件 2 + 测试 1 + 一处既有插件微调）——**未动引擎** |
| 规模现状 | 25 个插件 `tpc.toml`，共出现 **28 种段名**（`[analyzer]`/`[grammar]`/`[lexer]`/`[capabilities]`/`[[pipeline.units]]`/`[[formatter.categories]]`/…） |

散落面的构成（同一功能被**多个互不知晓的观测点**分别要求登记）：**插件内**
（`tpc.toml` 段声明 + 实现 `.py` + 规则表 `.toml`）／**引擎侧登记表**
（`core/_protocol.py` 契约键常量、`declare_cfg` 配置段、`tools/config_sites.py` 词汇白名单）／
**行为基线**（`tests/e2e/samples/*/expected.json`、`diag_baseline.json`、
`tools/baselines/min_pack_baseline.json`、变异注入器、`run_all_tests.py`）／**文档治理**
（插件 README、`linter_architecture.md`、`MODEL_INDEX.md`、CHANGELOG）。

判据：**同一事实被写在 ≥2 个必须手工保持同步的位置**（不是"文件多"本身——测试与文档
本来就该有；问题是**没有单一事实源**，靠人记着同步）。

### P-B 上游契约耦合：引擎一变，语言包被迫跟着改

实测（精化基座重构全程，26 提交）：`grammar/`（语言包侧）**11** 个文件、
`tests/` **11** 个、`analyzer/`（引擎侧）**10** 个被迫改动。即**一次引擎边界调整 →
语言包侧 11 个文件 + 测试侧 11 个文件跟着改**。这次改动本身值得（删掉约 1000 行引擎侧
语言知识），但**代价被记在了语言包账上**，而语言包是 tpc 对外的"资产范围"——代价会随
语言包数量线性放大（C 包、SV 包、用户标定包）。

### P-C 兼容入口：从"整条 API 线"改成"能力清单协商"

旧机制 `[engine] api = "0.1"` 是**整条 API 线**的 major.minor——引擎 minor 一动所有包都被拦，
且报错说不出**缺哪一项**。现役：`[engine] uses = [...]` 逐项声明依赖的引擎契约面，
能力表与版本语义在 `core/engine_capabilities.py`、协商在 `core/engine_compat.py`
（任一项不认识/版本不匹配 → 加载 fail-fast，**报错点名是哪一项**）；未声明能力的包
不受无关能力演进影响。升版判据：只有"该能力对语言包**可见地**变了"才 `+1`，
纯内部重构/性能/文案不升。

### 步 2 收敛目标与接受边界

**收敛结果**：诊断码的单一来源 = 声明式规则表 ∪ 插件 handler `code=` 字面量，抽成**一份
共用实现** `tests/_rule_codes.py`（两个门禁各自实现提取逻辑本身就是新的散点）；
三个机器可读登记点（变异注入器、`eval_benchmark` 映射、`diag_baseline` 计数键）接上校验后，
`check` 族接触点 **56 → 16**（中位 2→1、最大 5→3）。**门禁有效性（实测）**：注入假码
`ZZ999` → 该门禁 **1 failed**、还原 **0**；三处实际校验 **11 / 13 / 7** 条码（非空转）。
"已收敛/判保持"登记每条须有 `reason` + `source` 指向**真实存在**的门禁
（`tools/baselines/feature_sites_converged.json` / `tools/baselines/feature_sites_kept.json`），否则洗欠账只需写一行 JSON。
⚠ 踩过的坑：码形态正则写成 `[A-Z]{2,4}` 会把**单字母前缀码**（`W101/W201/W202` 等 8 个）
静默漏出校验面（已在两处注释显式记下）。

**剩余 16 点（未收敛，逐项已定性）**：

    6  analyzer/semantic_checks.md          机制文档的码表（散文/成范围出现，逐 token 校验会误报）
    5  tests/e2e/eval_check_accuracy.py     仅 docstring 里枚举码（可改为不枚举 → 真删除）
    2  tests/_check_test.py                 共用测试助手（若为迭代用，应改读单一来源）
    1  core/check_registry.py               规则表模块头 docstring 的示例码（文档，非登记）
    1  tools/check_gate_efficacy.py         变异目标（与注入器同理，可接同一门禁）
    1  analyzer/suppress.py                 抑制逻辑引用码（合理引用）

**接受的边界（有意不收敛）**：散文类（机制文档码表、docstring 枚举）**不**接逐 token
校验——会成范围（`NC001-NC010`）与历史提及出现，逐 token 校验是误报机器；这类由文档门禁
（`tests/policy/test_doc_stats.py`）+ 人工复核承担。判断标准始终是"**是否必须靠人记着
同步**"，不是"文件里有没有出现这个码"。

## 关联条目

- `docs/engine_overview.md`「横切机制」（现役机制清单：配置注册制 / 组件协议 / 核心类型 /
  token 协议）——本档讨论的是**这些机制之间的重复登记**，不推翻它们
- `core/engine_compat.py`（契约协商）、`core/engine_capabilities.py`（能力表与版本语义）、
  `core/config_registry.py`（配置段登记面）
- `policy/structural_budget.md` + `tools/baselines/structural_kept.json`（欠账口径与登记表先例）
- `tools/feature_sites.py`（接触点计量）+ 基线 `tools/baselines/feature_sites_baseline.json`
