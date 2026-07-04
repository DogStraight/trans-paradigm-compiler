# Session Summary — 2026-07-04

## 完成清单

### Bug 修复
- [x] **statement_rule_names 过滤条件** — `getattr(rule, "end_case") is not None` 因 `GrammarRule.__init__` 中 `end_case` 默认值为 `[]`，导致所有规则被加入候选列表。PortTail 在 `keyword.reg` 时优先于 `RegDecl` 匹配
  - 修复：改为 `getattr(rule, "end_case", [])`
  - 涉及：`parser/main_parser.py`、`verilog/run_pipeline.py`
- [x] **join 原语 group 展平 SoftLine** — `eval_join` 始终用 `group()` 包裹，`Root.layout = { join = "\n" }` 中 `"\n".rstrip()` 返回 ""，SoftLine 在 flat 模式变为空格，注释和 module 声明合并
  - 修复：分隔符为 `\n` 时用 `Break` 且不 group；空分隔符直接拼接
  - 涉及：`renderer/primitives/join_prim.py`
- [x] **ModuleDecl 端口 `)` 不在独立行** — `{ soft = true }` 在 port group 内，`group` flat 模式展平为空格。无端口时产生 `( )`
  - 修复：端口组添加 `ref = "ports"` + `{ break = true }`
  - 涉及：`grammar/rules_verilog/01_module.toml`
- [x] **模块声明 `);` 后无空白行** — head 尾部缺少换行
  - 修复：head 末尾添加 `{ break = true }`
  - 涉及：`grammar/rules_verilog/01_module.toml`
- [x] **NamedPortList 端口缩进错位** — `nest = 2` 与父级 body indent 叠加，`.port_b` 比 `.port_a` 多 8 空格
  - 修复：移除 `nest = 2`
  - 涉及：`grammar/rules_verilog/04_statements.toml`
- [x] **魔法数字 9999** — `rule_selector.py:153` 无意义硬编码
  - 修复：替换为 `_ORDER_NOT_FOUND`
  - 涉及：`parser/rule_selector.py`

### Customization 创建
- [x] **`.github/copilot-instructions.md`** — 项目约定（架构、TOML 规则、Renderer DSL、SemanticAnalyzer）
- [x] **`.github/skills/grammar-lint/`** — TOML 规则静态检查（8 类检查）
- [x] **`.github/skills/pipeline-debug/`** — 管线调试（5 步流程 + `diagnose.py` 脚本 + `--trace-token`）
- [x] **`.github/skills/renderer-debug/`** — 渲染调试（Doc IR 树、`trace_render.py`）
- [x] **`.github/hooks/git/commit-msg`** — 提交信息格式校验 (`type(scope): desc`)
- [x] **`~/.agents/skills/hardcode-check/`** — 硬编码扫描（个人级）
- [x] **`docs/debug_known_issues.md`** — 已知问题速查表

### 仓库维护
- [x] 删除 `stash`（`refs/stash@{0}`）
- [x] 删除 `agents/pointer-behavior-issue-log` 分支
- [x] 9 个 commit fast-forward 合并到 `dev`，保持单线历史
- [x] 清理 `.github/hooks/提交代码.json` + `check-changes.ps1`（冗余）

## 当前状态
- **分支**: `dev`（`7c98add`）
- **测试**: 31/31 通过
- **工作区**: 干净

## 待办
- [ ] function/task 语法支持（`copilot-instructions.md` 已记录架构，但规则未实现）
- [ ] 预处理器（`define` / `include` / `ifdef`）
- [ ] 多维数组声明 `reg [7:0] mem [0:255][0:7]`
- [ ] 常量折叠（编译期计算 `W-1`）
- [ ] 自动 diff 测试（gen/*.v vs ref/*.v）

## 关键决策
- Skill 放项目级 `.github/skills/`，不重复放个人级
- `copilot-instructions.md` 放 `.github/` 自动加载
- 渲染调试优先用 `trace_render.py --show-doc`
- 调试诊断优先用 `diagnose.py` + `--trace-token`
- 提交信息格式: `type(scope): description`
