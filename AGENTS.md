# TransParadigm (tpc) — 项目导览

配置驱动的语言流水线：语言规则写在 TOML（`grammar/`）里，引擎是通用骨架。
当前实例语言：Verilog（`grammar/verilog/`）、C（`grammar/c/`，核心基线 +
标准增量插件族）与 c4（`grammar/c4/`，从零搭出的示例语言）。

## 改任何子系统前

1. `docs/engine_overview.md`（全景）→ `docs/MODEL_INDEX.md`（跳转表：知识单元 →
   文档 → 实现 → 验证）
2. `docs/gaps/README.md` 对应部件档案：先确认"这算不算要改"，别把刻意接受的设计
   当 bug 修、或重复调研已否掉的方向
3. `docs/decisions/`（为什么）+ 就近架构文档（怎么拼）
4. 维护文件头 `Doc:` 反向引用（`policy/doc-alignment.md`）
5. 跑对应测试（`tests/`；改 linter 加跑 `tests/e2e/eval_lint_accuracy.py` 看 recall/误报）；
   守规约：`policy/coding-style.md`（注释/分区/命名）与 `parser/expression_conventions.md`；
   **改过哪个 py 就清哪个的静态诊断**（`policy/pylance-cleanup.md`）

## 硬约束

- **语言知识不进代码**：规则名、token 类型、结构名、表达式形态一律由
  `grammar/` TOML 配置、规则字段、推导提供，引擎不得硬编码任何语言具体知识。
- **配置加载 fail-fast**（`core/config_lifecycle.md`）：配置错误直接报错，不静默降级。
- **不留向后兼容**：行为/配置/接口过时即删，不保留兼容垫片、deprecated 路径或
  "旧版分支"——历史在 git log 可追溯，删除优于兼容，避免死代码与双路径漂移。
  与 TODO"完成即删"同纪律：过时的直接删，而不是标记弃用后挂着。
- **删除先证后删**：删除须命中判据（说不出判据不删），反判据不是删除对象——
  判据全表与反判据见 `policy/doc-alignment.md`「删除判据」。
- 文档分层只对协作方文档生效（`references.md` 等个人思考沉淀不对齐），见 `docs/README.md`。

## 协作行为（完整版见 `policy/collaboration.md`）

- **默认只本地提交，不推送**（作者说"推"才推）；文档措辞中性工程化。
- **先看成熟解法、不闭门造车**，不拉踩开源作者；借鉴点标 🔥/💡/📌，"不实现"写明原因；
  成熟工具输出可当 oracle（对拍验证）。
- **先落档后动手**；文档归位先判类（速查见 `docs/README.md`「放置速查」）。
- **分步分期**（每阶段独立验证、完成即提交汇报）；**缺陷先成因后动手**；**收尾给
  结论分级** `verified`/`partial`/`failed`，缺验证不算完成（只能报 partial）。
- **TODO/ROADMAP 只留未完成、完成即删**；每次收尾主动同步（无需提示）。

**指令文件自身纪律（AGENTS.md 修剪，细节见 `policy/collaboration.md`）：**
- 已能正确做就删；**不复制门禁**；**只用已成立或已明确同意的原则**；细节迁出
  （范式进 `policy/collaboration.md`，命令与清单进就近 README）——本文件是目录，
  不是百科，保持 ~100 行量级。

## 子系统

各目录职责与边界见 `docs/engine_overview.md`（管线一条线 + 子系统表）；逐文件一句话
见各子包 `README.md`。

## 运行

- 入口：`main.py`（CLI）
- 快速回归：`pytest -m smoke`（~12s，功能域代表层，日常改动先跑；分层见 `tests/README.md`）
- 全量测试：`pytest tests/`（零运行时依赖，无第三方包）
- 开发自查工具（都不进日常门禁，人工/按需跑）：**清单见 `tools/README.md`**
  （配置同步点位 / 增量覆盖率 / 门禁有效性抽查 / 隔离对照 / 现场转储 / 宏位置覆盖 /
  外部审计 Bifrost；真实语料误报基线在 `tests/e2e/eval_diag_baseline.py`）
