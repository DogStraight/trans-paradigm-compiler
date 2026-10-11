# parser/ — 改这里的注意事项

> 上层制度见根 `AGENTS.md`；文件清单见 `parser/README.md`（逐文件一句话）。
> 本文件只写"改这个目录需要知道的"，不复制上层已说的内容。

- **不含语言知识**：production 规则全来自 `grammar/` TOML；改引擎时不得出现语言具体字符串
  （`python tools/check_hardcode.py --strict-lang` 拦）。
- **注释归属是收敛过的高危面**：判定单点在 `_comment_trivia.py`（模块 docstring 有通道分工表）。
  改动前先读它——历史上"同一判定三处实现"曾造成语义不一致。
- **快照必须成对**：`_repeat_loop` / `match_productions` 里的 `create_snapshot` 必须配
  `restore_snapshot`；符号 store 的还原另有测试（`tests/engine/parser/test_symbol_rollback.py`）。
- **raw 承载（P3c 起）**：语句位 raw 必须**消费整个语句区间**，否则 truncation 会判失败停管线；
  直出依赖节点的 `_verbatim_text`（先例 = 宏 splice），**不要改 renderer**。
- 改本目录必跑：`pytest tests/engine/parser -q`，以及 `python tests/e2e/eval_lint_accuracy.py`
  （语法面改动会影响 linter 的候选收敛）。
