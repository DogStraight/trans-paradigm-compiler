---
name: project-research
description: 调研外部项目，评估对 tpc 的参考价值。输出差异对比、存续状态、可借鉴部分。
user-invocable: true
argument-hint: '<项目名或 GitHub URL>'
---

# Project Research — 外部项目调研

调研外部解析器/编译器/DSL 项目，评估对 tpc Compiler 的参考价值。

## 调研流程

### 1. 项目发现

- 若用户给出项目名 → GitHub / GitLab / crates.io / PyPI 搜索
- 若给出 URL → 直接抓取 README、文档、源码结构
- 优先找**公开仓库**，纯论文项目标注"无公开代码"

### 2. 三维输出

每项调研必须覆盖以下三点：

**① 差异对比**（与 tpc 的架构差异）

| 维度 | 该项目 | tpc |
|------|--------|-----|
| 解析算法 | | 递归下降+回溯 |
| 规则格式 | | TOML production |
| 扩展方式 | | EXT inject |
| AST 处理 | | Normalizer + Transform |
| 代码生成 | | Doc IR Renderer |
| 语言 | | Python 3.11+ |
| 依赖 | | 零外部依赖 |

只填有差异的维度，相同或无关的跳过。

**② 存续状态**

- 最后更新时间
- Stars / 下载量 / 社区活跃度
- 版本号（是否 < 1.0）
- 维护状态：活跃 / 停滞 / 已归档 / 已删除
- 已知缺陷或未完成的 TODO

**③ 值得参考的部分**

列出具体可借鉴的设计或实现，标注参考层级：

| 层级 | 含义 |
|------|------|
| 🔥 直接借鉴 | 设计思路可直接移植 |
| 💡 启发 | 思路有价值但实现路径不同 |
| ⚠️ 避坑 | 犯过的错误值得警惕 |
| ❌ 无价值 | 对 tpc 无参考意义 |

### 3. 写入 references.md

结论写入 `docs/references.md` 表格，一行：

```
| **项目名** | 关系 | 一句话价值总结 |
```

关系取：深度参考 / 设计参考 / 架构对比 / 概念参考 / 无价值

## 工具使用

- `fetch_webpage` — 抓取 GitHub README、docs.rs、crates.io 页面
- `github_repo` / `github_text_search` — 搜索仓库源码
- 不写代码，只读调研

## tpc 核心特征（对比参照）

调研时始终对比以下 tpc 特征：

- **配置驱动**：TOML 定义语法，零硬编码 Verilog 逻辑
- **递归下降+回溯**：非生成式，snapshot/restore
- **Pratt 表达式**：`_symbol_level.toml` 声明优先级
- **Doc IR 渲染**：Wadler-Lindig 算法
- **EXT 注入**：production injection，非继承/覆写
- **零外部依赖**：Python 3.11+ 标准库
- **E2E 测试**：不写单测，全量回归
