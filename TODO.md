# TODO（短期待办清单）

> 完成项/完成历史看 git log + 测试套件，本文件只列未完成待办。
> 中长期目标（backlog/非发布阻塞/v0.2 候选）见 `ROADMAP.md`，不在本文件。

## P1 — Verilog 实例完善

### P1.6 include 指令形态外置（预处理器外置线剩项）

预处理器形态外置已完成（形态 / 实参 / 后缀 / 处置策略 / 注释标点 / 续行 / 指令行切分），
仅剩 include 一处：

- `primitives/include.py` 的 `_INCLUDE_RE` / `_INCLUDE_ANGLE_RE` 硬编码
  `` `include ``（前缀 + 关键字拼写）与路径定界符 `"..."` / `<...>`；handler 还
  `del prefix, _name` 忽略调用方传入的声明值 → 语言包换前缀（或换语言）时 include
  静默失效。语料实测：138 样本里 `<...>` 形态 0 处、含 include 仅 2 文件（影响面窄）。
- 待定声明面（拟放**既有** `[directive_handlers.include]`，该表已有
  `enabled` / `search_dirs` / `silent`）：路径形态列表（开 / 闭 / 是否相对路径优先），
  关键字取用改走 `primitives/registry.py::split_directive`。

## 外部审计修复（Bifrost 全仓诊断，2026-09-18 起）

> 清单与处置记录：`_drafts/bifrost/findings.md`、`_drafts/bifrost/dispositions.md`
> （工作草稿，不进 git）。范围按作者定调：只修非 tests；每批跑 smoke +
> `check_doc_refs` + `check_hardcode`，批末跑全量测试。完成即删对应条目。

- **B-A 异常吞吃 triage**（44 条）：score 10 的空体 `except Exception: pass`
  逐条定成因 → 修 / 写明兜底理由 / 记为已知边界；最重一条是
  `pipeline._load_pipeline_defaults`（与"配置加载 fail-fast"张力最大）。
- **B-B 复杂度/长方法重构**（大改，分部件分批）：`analyzer/structure.py`
  （1082 行 / CC 73）、`lexer/main_lexer.Lexer.tokenize`（397 行）、
  `grammar/verilog/plugins/formatter/boundary.py` 的 `build_block_tokens` /
  `BoundaryScanner._scan_tokens`（249 / 319 行）、
  `parser/pratt_parser.parse_expression`（310 行）。
- **B-C 结构重复**（非 tests 107 组）：跨插件重复抽公共助手
  （`case_check._const_value` ↔ `latch_check._const_value`、
  `always_check._target_sig` ↔ `latch_check._target_sig` 等）。

> 审计外观察（不在本清单）：`_eval_gen_cond` 的 `!PARAM` 特判是 Verilog 形态
> 进了引擎，与"本模块零语言知识"的声明相左——归 `docs/gaps/gap-semantic-elaboration-boundaries.md`
> 边界 2（引擎约定 vs 语言包声明）那条线，待语言包声明条件求值面时一起处理。

## 测试基础设施

- **全量并行跑偶发失败（预存在，成因未定）**：`tests/engine/core/test_language_switch.py::
  test_plugin_scope_excludes_other_language`——切到 verilog 后 `active_plugin_classes()`
  仍含 c4 的 `AsmGenPlugin`。实测：带/不带 2026-09-18 那批改动都会出现（3 跑 2 败 / 2 跑 1 败）
  → 非该批引入；单跑与 `-n0` 不复现；`PYTHONHASHSEED` 0..7 全过；
  `tools/check_test_isolation.py` 160 OK / 0 FAIL。待定位：并行 worker 下
  `_components_initialized` / `_active_components` / `_plugin_origins` 三者何时不同步。
