# tools/policy/ — 制度与门禁工具

> 制度（"该怎么做"）文档与机器化门禁工具同层（2026-09-05 制度文档归拢）——
> 制度由工具强制，工具是制度的执行者；引用入口：模型看 `AGENTS.md`、
> 人看 `CONTRIBUTING.md`。

## 制度文档

| 文档 | 制度 | 门禁工具 |
|------|------|----------|
| `coding-style.md` | 代码风格（注释语言/分区标题/命名） | `check_hardcode.py`（规则 1-4） |
| `doc-alignment.md` | 文档↔代码对齐约定（`Doc:`/`Impl:`/`Test:` + MODEL_INDEX 三处同步） | `check_doc_refs.py` / `doc_sync.py` |
| `release-checklist.md` | 发布 SOP（回归门禁 → 版本 → build → 包验证 → wheel 冒烟 → tag） | （人走流程，发布收尾） |
| 设计依据与删除判据 | `docs/decisions/0011-doc-governance.md`（ADR-0011） | `check_doc_refs.py` / `doc_sync.py` |

## 门禁工具

| 工具 | 强制 | 运行 |
|------|------|------|
| `check_hardcode.py` | 硬编码规范（路径/语言知识不进代码） | `python tools/policy/check_hardcode.py` |
| `check_doc_refs.py` | 文档调用点完整性（D1/D2 gate + D3/D4 info） | `python tools/policy/check_doc_refs.py` |
| `doc_sync.py` | rename/delete 文档时引用同步层 | `python tools/policy/doc_sync.py rename/delete ...` |

> 关联：制度机器化不重复写进 `AGENTS.md`（门禁强制的项由工具报，AGENTS 只
> 留范式）；`tools/policy/` 无 `__init__.py`（命令行工具，非包）。
