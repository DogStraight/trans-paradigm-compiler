# ADR-0023: 档位门控——可选组件的 grammar 文件随 `enabled` 加载

- Status: accepted
- Date: 2026-10-21（#39 调查轮出决策材料 → 作者拍板"只能走 A" → #40 实现）
- 关联：ADR-0021（原"暂缓"行取回并删除）、`docs/gaps/gap-language-pack-scope.md`「运行时档位」、
  `docs/gaps/gap-engine-abstraction-audit.md` #1

## 背景

`[plugins] enabled` 长期只门控**声明面**（token/number 等声明合并）；插件**规则文件**由
`setup_grammar` → `load_all_components(<pack>/plugins)` **无条件**加载、注入随之上膛。于是
「档位 = 接受域」对**不依赖新关键字的增量**不成立（C23 的 `[[属性]]` 是最初一例），并卡住
两条 C23 合法标准代码：`_Static_assert(1)`（下划线拼写、单参）与 `enum e : int`——#38 已证
两者都**无法**收敛到声明层（对照实例见 gap「运行时档位」）。

作者 2026-10-21 拍板取档位门控（并强调**提交节点要小心**：本轮一个原子提交，行为变化、
引擎修复、测试与文档同步落地）。

## 决策

1. **可选件** = 包内 `[plugins] enabled` 清单里列出的组件名；**未列出的组件是常驻件**
   （C 的 `semantics` / `checks/*`、c4 的 `asm_gen`），其 grammar **恒加载**。
2. 可选件的 `[grammar] files` 只在**当前档位**含该组件名时加载；档位来源 = 显式
   `enabled=` 覆盖 > `load_language` 登记 > 包内清单（沿用既有优先级）。
3. **Python 组件永不按档位门控**（handler / postpass 是"怎么分析"，不是"收哪些语法"；
   门控它们会让基线档失去符号/检查基座）。
4. 门控实现在**消费面**：`ConfigRegistry.tier_state(rules_dir)` →（可选件清单, 档位）→
   `load_all_components(declared_optional=…, active_tier=…)` → `get_component_grammar_files`
   过滤。非语言包目录（低层契约 / 临时目录）两者皆空 ⇒ 不过滤（旧行为）。
5. 配套引擎修复（门控暴露的两个旧缺陷，缺一即挂）：
   · **空槽位不可匹配**：非块规则 + `production = []` 是"没有形态"，不是"匹配空"
     （门控后基线档首次出现**未被注入**的空槽位；旧语义下 `@Slot*` 迭代项零进展 ⇒
     repeat 死循环 + 属性绑定告警风暴，实测挂起）；
   · **repeat/plus 零进展守卫**：元素若空匹配（零 token）不算一次迭代，`+` 达不到
     min_count 即失败。

## 被否备选

- **B 维持现状**：合法标准代码持续被拒，与阶段 5 标准等效目标冲突；否。
- **按"名字 ∈ enabled"门控整棵组件树**：C 的 `semantics`/`checks` 是常驻件（不在清单里、
  无 grammar），会被误伤；否。
- **在 C 包内用 Python 组件按档位注入**：绕过契约、把档位判断藏进语言包；否。

## 后果

- **C 包**：基线/c11/c17 档不再加载 c23 规则 ⇒ **纯语法增量也受档位**（`[[属性]]` 从
  c23 档起，行为更严格、方向 = 接受域）；两条标准缺口解锁（后续轮实现）。
- **verilog / yaml / c4**：零行为变化（verilog 的 9 个 grammar 组件全在 enabled 清单里；
  yaml 无组件；c4 仅 transform 组件）。
- 代价：`enabled` 语义从"声明面"扩为"声明面 + 可选件 grammar"，机制文档与测试同步。
- 边界：`ext_dirs`（显式额外规则目录）不参与门控——它本就是"调用方点名加载"。

## 验证

- 引擎：`tests/engine/core/test_tier_gated_grammar.py`（规则表随档出现/消失、常驻组件不被
  误伤、相对/绝对两种包路径风格的档位查询、非包目录退化为不过滤）；
  `tests/engine/parser/test_production_engine.py::TestRepeatZeroProgress`（空匹配元素收敛）。
- 语言：`tests/languages/c/test_c_standard_tiers.py`（31 构造 × 4 档矩阵；属性行改为 c23 起；
  空槽位基线档回归）；`tests/languages/c` 全量。
- 跨语言零回归：全量 `pytest tests` + `tools/ab_pipeline_compare.py --mode cli --products`
  （verilog 0/144）。

> Impl: `parser/__init__.py::setup_grammar`；`core/plugin_loader.py::{load_all_components,
> get_component_grammar_files,_grammar_tier_allows}`；`core/config_registry.py::tier_state`；
> `parser/_production.py::{try_plain_rule,_repeat_loop}`
> Test: `tests/engine/core/test_tier_gated_grammar.py`、`tests/languages/c/test_c_standard_tiers.py`
