# policy/ — 制度与门禁工具

> 制度（"该怎么做"）文档与机器化门禁工具同层（2026-09-05 制度文档归拢）——
> 制度由工具强制，工具是制度的执行者；引用入口：模型看 `AGENTS.md`、
> 人看 `README.md` 的 Contributing 节（链 AGENTS + MODEL_INDEX + 门禁）。

## 制度文档

| 文档 | 制度 | 门禁工具 |
|------|------|----------|
| `coding-style.md` | 代码风格（注释语言/分区标题/命名） | `check_hardcode.py`（规则 1-4） |
| `collaboration.md` | 协作行为范式（克制推送 / 见贤思齐 / 实施节奏与结论分级 / TODO 纪律）+ 指令文件自身纪律 | （行为约定，无工具） |
| `doc-alignment.md` | 文档↔代码对齐约定（`Doc:`/`Impl:`/`Test:` + MODEL_INDEX 三处同步）+ 引用纪律（锚机制不锚 ADR）+ 删除判据（先证后删） | `check_doc_refs.py` / `doc_sync.py` |
| `engine_config_sync.md` | 引擎语义/键名变更的配置同步规程（四步“翻译”式：定位语言包 → 取配置字典 → 整键匹配 → 逐项替换；子串误伤防范） | `tools/config_sites.py`（`list` / `check` / `rename`，开发自查，见规程） |
| `pylance-cleanup.md` | 改过哪个 py 就清哪个的静态诊断（含静/动态双面清理） | （人按需跑，无门禁） |
| `bifrost_audit.md` | 外部审计规程（Bifrost 结构面信号：影响面/复杂度/异常吞吃/死代码/弱断言；先小后大） | （外部工具，开发自查） |
| `structural_budget.md` | 结构欠账的度量与停止判据（超额量口径 R1–R5 / 结构欠账分 S / ROI 决策 / 三条停止规则） | `tools/structural_score.py`（开发自查，需外部二进制） |
| `release-checklist.md` | 发布 SOP（回归门禁 → 版本 → build → 包验证 → wheel 冒烟 → tag） | （人走流程，发布收尾） |

## 门禁工具

| 工具 | 强制 | 运行 |
|------|------|------|
| `check_hardcode.py` | 硬编码规范（路径/语言知识不进代码） | `python policy/check_hardcode.py` |
| `check_doc_refs.py` | 文档调用点完整性（D1/D2 gate + D3/D4 info） | `python policy/check_doc_refs.py` |
| `doc_sync.py` | rename/delete 文档时引用同步层 | `python policy/doc_sync.py rename/delete ...` |

> 关联：制度机器化不重复写进 `AGENTS.md`（门禁强制的项由工具报，AGENTS 只
> 留范式）；`policy/` 无 `__init__.py`（命令行工具，非包）。
