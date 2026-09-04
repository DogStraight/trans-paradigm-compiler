# ADR-0012: 文档工程对标缺口（引擎叙事 / 术语表 / 变更记录义务）

- Status: draft（2026-09-05 对标调研结论，未立项设计输入；立项实现时升
  accepted，机制落部件后收敛/删除——沿 decisions/README 状态流）
- Date: 2026-09-05

## 背景

文档治理就近化已闭环：机制→子包、ADR≤10、gaps 档案、policy 制度、
references 只调研、Doc:/Impl: 双向 + check_doc_refs/doc_sync 门禁、删除判据。
在此基础上对标知名项目"文档工程"找剩余缺口。对标来源（2026-09-05，
agent-reach/web 采集）：Diátaxis 分类法、CPython devguide（blurb 变更记录
+ sphinx-lint PR 门禁）、rustc-dev-guide（组织形态 + 附录 glossary）、vale
（docs-as-code 散文 lint）；K8s sig-docs / LLVM 按通用认知轻量带过。

对照结论：

- **Diátaxis 四象限不适用**——面向**用户文档**（tutorial/how-to/reference/
  explanation 按读者需求分）；tpc 体系是**协作方/开发文档**（决策/机制/缺口/
  制度/调研/索引），已有自建 8 类分流，且多出 decisions/gaps/policy/research
  这些 Diátaxis 完全不管的治理维度。tpc 现有映射：tutorial≈language_walkthrough；
  how-to≈.agents SKILL（读者是模型）；reference≈grammar_rule_fields/MODEL_INDEX/
  api.md；explanation≈decisions + 子包架构文档。
- **tpc 治理已上游**：就近化 + MODEL_INDEX 三方跳转（doc→impl→test）+ 内部
  引用门禁，在 OSS 里属前列。真正缺口集中在一个高信号项 + 几个治理死角
  （见决策）。
- **不借鉴**：vale/markdownlint 引入（英文工具；tpc 文档中文主体 + 零第三方
  依赖自研 policy 模式）；Diátaxis 直接套用（服务对象不同）；K8s OWNERS 协作
  治理（单作者过重）。

## 决策（draft 方向，未立项）

**G1 引擎整合叙事缺失（🔥 高，TODO「文档分层落地」残余信号）**
就近化后没有"整个引擎怎么拼"的连贯入口（rustc-dev-guide 在 rustc 承担的角色）：
MODEL_INDEX 是**跳转表非叙事**、pipeline_stages 只讲层间边界、AGENTS 是协作
纪律非引擎介绍。新协作方/模型想从零理解全景，没有单一连贯阅读物。
倾向：补引擎总览叙事。落点待定（docs 教程层 / MODEL_INDEX 前置叙事 / 新
document），不改现有就近机制文档——与 rustc"独立 dev-guide 缓解源码即文档
不可导航"同动机。

**G2 术语表缺失（💡 中低、低成本）**
Doc IR / pass / slot / postpass / capability / world A·B / inject / fragment
等术语分散定义于各机制文档，无集中 glossary（rustc-dev-guide 附录有）。
倾向：作 G1 叙事的伴生产物或独立术语表（落点待定）。

**G4 CHANGELOG 日常义务无强制位（💡 中低）**
release-checklist 只在发布归拢（Keep a Changelog，Unreleased 手动详条）；
CPython blurb 的"变更必带记录"是 PR 级机器门禁。单作者场景不取机器门禁，
取纪律位：AGENTS"闭环即主动更新 TODO/ROADMAP"并列补"检查 CHANGELOG
Unreleased"（收尾固定环节）。

（G3 外链健康无门禁 / G5 散文术语一致性无 lint / G6 文档示例未测试执行 →
📌 观察项，本次不立项；可记 gaps 边界或 references 对照，不重复落档。）

## 权衡

- 采纳 G1：牺牲"就近即读"的纯粹性，换新协作方/模型从零理解全景的低成本入口。
- G1 与 MODEL_INDEX 分工：MODEL_INDEX 保持跳转表；叙事是连贯阅读物，不互相
  替代、不重复承载同一知识。
- G1 落点（docs 教程层 vs MODEL_INDEX 前置 vs 新 doc）与 language_walkthrough
  的边界：walkthrough 面向"从零搭一门语言"（语言包作者），引擎叙事面向
  "理解引擎怎么拼"（引擎/协作方）——draft 期悬而未决，实施前定。
- 不采纳项见背景"不借鉴"清单。

## 验证（待实现）

- G1 立项：产出叙事文档 + MODEL_INDEX/导航登记（D4 不孤儿）+ 相关 Doc: 关联。
- G2 立项：术语表文件 + 文档链到术语表。
- G4：AGENTS 收尾纪律位补 CHANGELOG 检查（靠纪律，无机器门禁）。

> Impl: 待实现
> Test: 待实现
