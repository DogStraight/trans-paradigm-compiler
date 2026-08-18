# 代码质量审计报告

> 日期：2026-08-18
> 目的：全项目代码质量摸底——规模基线、强项、弱项（复杂度/约定执行/卫生问题）。
> **只摸底，不改代码**。发现按严重程度分类，标注建议优先级，供后续排期。
> 审计范围：core/ lexer/ parser/ linter/ analyzer/ transform/ renderer/ preprocessor/
> + grammar/ 两个语言包 + tests/ + docs/ + main.py。
> 验证基线：667 测试全过（10.65s）、git 工作区干净、零运行时依赖。

---

## 规模与测试基线

| 指标 | 数值 |
|------|------|
| Python 文件 / 行数 | 160 文件 / 27,768 行 |
| TOML 语法文件 | 49 个（verilog 37 + c4 11） |
| 测试函数 / 文件 | 553 个 / 48 文件（8,951 行） |
| 测试通过率 | 667 passed |
| 测试/代码比 | ~32% |
| git 提交 / 工作区 | 43 提交 / 干净 |
| 运行时依赖 | 0 |

## 强项（维持现状，无需改动）

### S1. 测试体系
- 覆盖全部 8 个子系统，无零测试模块
- e2e 用真实项目做回归守卫：PicoRV32（8 module 结构断言）、darkriscv、tv80、SERV，
  带保真度阈值（0.80）与幂等检查（format×3 稳定）
- lint 精度独立评估脚本 `tests/e2e/eval_lint_accuracy.py`（recall 100% / 0 误报）
- 测试有"为什么存在"的背景说明与断言意图

### S2. 架构主张有实证
- 语言知识全在 TOML，引擎语言无关——c4 第二语言（.c → c4 VM 汇编）验证主张
- grammar 引用完整性良好：165 规则定义 / 143 个 @Call 引用，无悬空引用、无重复规则名

### S3. 文档-代码链接体系
- `MODEL_INDEX.md` 跳转表 10 个 Impl 引用全部有效（文件 + 符号均存在）
- 4 个 ADR 决策记录、配置生命周期/表达式约定等架构文档齐全
- IEEE 1364-2005 / 1800-2023 Annex A 已提取为可检索 BNF

### S4. 注释质量
- 大量解释"为什么"的注释（如 matcher 的 `consumed` 从入参起算的原因、end_case
  三分类教训），而非复述"做了什么"

### S5. 工程卫生
- 核心代码无 TODO/FIXME 残留、无编译错误
- 统一异常层级（`TransParadigmError` + 6 子类）、fail-fast 配置加载
- 调试基础设施（失败报告/日志分级/停点 trace/行号对账）

---

## 弱项（按严重程度排序）

### 🟠 W1. 核心函数复杂度偏高

31 个超长函数（>60 行）、33 个高圈复杂度（>15），集中在核心路径：

| 函数 | 行数 | 圈复杂度 |
|------|------|---------|
| `lexer/main_lexer.py::tokenize()` | 374 | 58 |
| `linter/checkers/matcher.py::_match_call_impl()` | 151 | 48 |
| `transform/normalizer.py::_normalize()` | 115 | 41 |
| `lexer/number_gen.py::compile_number_pattern()` | 174 | 39 |
| `transform/config_driven.py::_expand_primitive()` | 128 | 39 |
| `parser/pratt_parser.py::parse_expression()` | 180 | 32 |
| `linter/discovery.py::_discover_range()` | 160 | 32 |
| `core/config_registry.py::load_all()` | 141 | 31 |
| `linter/lookahead.py::_feat_token_paths()` | 69 | 31 |
| `parser/_production.py::try_rule_productions()` | 166 | 29 |

这些是状态机/递归下降的常见形态，但 `tokenize()` 374 行 CC=58 已超出可读性舒适区。
**重构风险高**（有 667 测试兜底，可逐步拆分），建议作为长期优化项而非紧急项。

- 建议：长期。按"状态机分支 → 独立方法"渐进拆分，每步跑全量测试。

### 🟠 W2. `Doc:` 反向引用约定执行不彻底

`docs/README.md` 约定"新增知识单元三处同步：文件头 `Doc:`、文档 `Impl:`、
`MODEL_INDEX.md`"，但实际只有 2 个文件有 `Doc:` 引用（`core/config_registry.py`、
`linter/scanner.py`），MODEL_INDEX 有 10 个条目。**链接是单向的**——从文档能到代码，
从代码回不到文档。

- 建议：中成本。为 MODEL_INDEX 中 10 个条目对应的模块文件头补一行 `Doc:` 引用。

### 🟡 W3. 测试硬编码绝对路径

4 处测试硬编码 `e:\project\tpc_compiler\grammar\verilog`：

| 文件 | 行 | 说明 |
|------|----|------|
| `tests/linter/test_diagnose.py` | 17 / 34 / 52 | `diagnose_all_paths(src, rules_...)` |
| `tests/preprocessor/test_primitives.py` | 38 | `"rules_dir": r"e:\project\tpc_compiler\grammar\verilog"` |

换机器/换目录会挂，应改用 `DEFAULT_RULES_DIR` 或 fixture。

- 建议：低成本高收益，半小时内可完成。

### 🟡 W4. 少量未使用导入

约 5-6 处真问题（其余为 `__future__`/相对导入/re-export 误报）：

| 文件 | 导入 |
|------|------|
| `parser/parser_core.py` | `from rule_selector import _compute_start_tokens`（私有符号） |
| `parser/_constants.py` | `COMMENT_TOKEN_TYPE` / `IDENTIFIER_TOKEN_TYPE` / `NEWLINE_TOKEN_TYPE` |
| `linter/checker.py` | `from dataclasses import field, asdict` |
| `analyzer/primitives/registry.py` | `from typing import Any` |

- 建议：低成本，随 W3 一并清理。

### 🟡 W5. 跨文件重复逻辑

`lexer/number_runner.py <-> lexer/number_fsm.py` 有相似的数字处理逻辑
（`trimmed = token.rstrip("_")` 等）。其余 196 个重复块均为同文件内状态机/分发器
模式重复（可接受）。

- 建议：低优先级，仅在重构 number 子系统时顺带处理。

---

## 已记录的技术债（roadmap/TODO 已覆盖，非本次新发现）

| 编号 | 内容 | 位置 |
|------|------|------|
| P2.0 | 配置生命周期机制（declare_cfg 三阶段时序）反直觉 | `docs/config_lifecycle.md` |
| P2.1 | 数字形态硬编码盲区（NumberFSM 全局单例，已部分配置化） | TODO.md |
| P1.3 | SV 插件化（已摘除内嵌 SV 特性，待独立语法实例） | TODO.md |
| P1.8 | Verilog 语法补全 + 仿真语法插件化（发布前置） | TODO.md |
| P1.4 | wrap 折行 end_case 分号化（试点 6 条，剩余待验证） | TODO.md |

---

## 建议优先级

| 优先级 | 项 | 成本 | 收益 |
|--------|----|------|------|
| P0 | W3 测试硬编码路径 + W4 未使用导入 | 半小时 | 可移植性 + 卫生 |
| P1 | W2 补全 `Doc:` 反向引用 | 中 | 文档双向链接闭环 |
| P2 | W1 拆分超长函数 | 长期渐进 | 可读性/可维护性 |
| 维持 | S1-S5 现有体系 | — | 无需大改 |

## 审计方法备注

- 复杂度：AST 静态分析（函数行数 + 分支计数圈复杂度）
- 重复代码：5 行滑动窗口哈希（跨文件）
- 引用完整性：`[RuleName]`/`[RuleName.xxx]` 表头 vs `@Call` 引用
- 文档链接：`Doc:` 正则 + MODEL_INDEX `Impl:` 文件/符号存在性
- 硬编码：`~/.agents/skills/hardcode-check/scripts/scan_hardcode.py`（3034 条中
  绝大多数为注释/测试数据/版本号误报，仅 4 处测试路径为真问题）
