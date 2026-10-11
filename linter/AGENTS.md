# linter/ — 改这里的注意事项

> 上层制度见根 `AGENTS.md`；文件清单见 `linter/README.md`，架构见 `linter/linter_architecture.md`。
> 本文件只写"改这个目录需要知道的"。

- **不含语言知识**：规则名 / token 类型 / 结构名一律来自 `grammar/` TOML（反解析器复用同一语法）。
- **资格判定的四条缺陷态已进门禁抽查**（`tools/check_gate_efficacy.py`）：去掉试解析 / 去位置
  先后 / 去 kind 过滤 / 去深度守卫 ⇒ 必须**各自变红**；改判定必须同步维护这四条。
- **packrat memo 以 token 位置为键**：改型试解析（`_substitution_trial`）前必须
  `RuleMatcher.memo_suspended()`，否则旧结果会被命中（实测踩过，目标句被误判失败）。
- **内部 warning 不进用户面**：`internal_warnings()` 只供后续阶段按行/列消费，
  不得进诊断 / `--json` / exit code。
- 改本目录必跑：`pytest tests/engine/linter -q` 与 `python tests/e2e/eval_lint_accuracy.py`
  （recall 33/33、误报 0 是门禁）。
