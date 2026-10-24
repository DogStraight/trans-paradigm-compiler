# linter/ — 改这里的注意事项

> 上层制度见根 `AGENTS.md`；文件清单见 `linter/README.md`，架构见 `linter/linter_architecture.md`。
> 本文件只写"改这个目录需要知道的"。

- **不含语言知识**：规则名 / token 类型 / 结构名一律来自 `grammar/` TOML（反解析器复用同一语法）。
- **门禁**：本目录的变异登记在 `tools/check_gate_efficacy.py`（`--list` 看当前条目）；
  改判定/匹配逻辑须同步维护对应条目（`tests/policy/test_gate_efficacy_mutations.py` 守静态一致性）。
- **packrat memo 以 token 位置为键**：同一 token 区间在不同语境下的匹配结果不可复用——
  新增"同区间、不同假设"的试解析时，必须先挂起 memo，否则旧结果会被命中（实测踩过，
  目标句被误判失败）。
- **内部中间结论不进用户面**：诊断 / `--json` / exit code 只应承载用户可见错误，
  内部收敛证据留在内部。
- 改本目录必跑：`pytest tests/engine/linter -q` 与 `python tests/e2e/eval_lint_accuracy.py`
  （recall 33/33、误报 0 是门禁）。
