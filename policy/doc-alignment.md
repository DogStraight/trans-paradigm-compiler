# 文档对齐约定（文档 ↔ 代码双向定位）

> 制度：原 `docs/README.md`「注释对齐约定」段，2026-09-05 抽出与门禁工具同层
> （`policy/`）——制度由工具强制：`check_doc_refs.py`（D1/D2/D3/D4 门禁）+
> `doc_sync.py`（rename/delete 引用同步）。目的：模型维护时**直接跳转**到
> 实现/验证位置，不做模糊搜索。

## 1. 代码 → 文档（`Doc:`）

每个模块文件头 docstring 末行声明对应文档条目：

```python
"""
scanner.py — 两阶段 Linter 编排器。

Doc: linter/linter_architecture.md   # 文件级引用（稳定，不随章节锚点漂移）
"""
```

## 2. 文档 → 代码（`Impl:` / `Test:`）

文档关键章节/ADR 条目声明实现与验证位置，精确到符号：

```markdown
> Impl: linter/scanner.py::LinterScanner.scan
> Test: tests/engine/linter/test_linter_discovery.py
```

## 3. 跳转表（`MODEL_INDEX.md`）

所有对齐条目的汇总表——模型改造前的第一站。新增对齐时同步更新该表。

## 维护规则

- **新增知识单元**（新模块/新决策/新机制）：三处同步——文件头 `Doc:`、文档 `Impl:`、`MODEL_INDEX.md` 一行。
- 引用的是"知识单元"级对齐（模块/关键符号），**不是每行注释**——避免成为新的维护负担。
- 符号重命名后更新 `Impl:` 与 `MODEL_INDEX.md`（grep `::` 可全量核对）。

## 引用纪律（锚稳定机制，不锚 ADR）

**`docs/decisions/`（ADR）是经常变动的部分**——accepted 完成即删、编号可复用、
长期 draft 并入 ROADMAP 后删（历史 git log）。因此：

- 代码 `Doc:` 头 / `MODEL_INDEX` 导航 / 正文叙述引用一律指向**稳定的机制文档**
  （子包架构文档、README、policy 制度），**不引 `decisions/NNNN-*.md` 作锚**。
- 机制文档要提"为什么/决策出处"时，**内联简短说明**（事故/动机一句话），不写
  "见 ADR-NNNN" 委托编号——ADR 删了委托就断。
- ADR 文件内部（如 `superseded by NNNN`）与 `decisions/README.md` 属例外
  （同层引用）。
- 归档已删 ADR 时：把机制文档里的 "决策依据见 ADR-NNNN" 改为内联"为什么"，
  Doc:/导航改指机制落点；正文里的 `（ADR-NNNN）` 决策标签可保留为历史编号
  （git log 可追）或改指机制，不新增此类引用。

## 门禁与同步

- `check_doc_refs.py`：D1（Doc: 目标存在）/D2（导航索引条目存在）gate +
  D3（Impl:/Test:）/D4（孤儿）info。
- `doc_sync.py`：rename/delete 时批量清理机械可清引用（Doc: 行 / 索引表格行），
  正文叙述引用（`references.md「章节」`）列人工清单。
- 设计依据与删除判据：`docs/decisions/0011-doc-governance.md`（ADR-0011）。
