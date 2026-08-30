---
name: agent-reach
description: '用 agent-reach 做项目调研的信息采集：结构化读取 GitHub 仓库、网页正文、Hacker News、RSS、MCP 注册表（全零配置免登录渠道）。适用于项目调研、竞品分析、技术选型前的信息收集。'
user-invocable: true
argument-hint: '调研目标，如"调研某 GitHub 仓库"或"搜索某主题"'
---

# Agent Reach 项目调研采集

## 适用场景

- 项目调研 / 竞品分析 / 技术选型前的信息收集
- 需要"正文级"信息（GitHub 仓库详情、网页清洗后正文、社区讨论），
  web_search 只有 snippet 不够时
- 只使用**零配置免登录**渠道：github / web / hacker_news / rss / mcp_registry
  （reddit/twitter/youtube 等需登录或流媒体渠道不启用）

## 前置

- CLI 已装（`uv tool install` 的 agent-reach v1.13.0）
- 检查渠道状态：`agent-reach doctor --json`（8 ready 为正常基线，
  reddit/twitter/youtube/searxng/crawl4ai 的 warn/off 是设计状态，不配置）

## 命令模板（全部 `--json` 输出结构化结果）

### GitHub 仓库/搜索（核心渠道）

```powershell
# 读仓库详情：stars/forks/license/language/时间线/描述
agent-reach collect --channel github --operation read --input "owner/repo" --json

# 搜索仓库
agent-reach collect --channel github --operation search --input "query" --limit 10 --json
```

### 网页正文（Jina Reader 清洗，去 HTML 标签）

```powershell
agent-reach collect --channel web --operation read --input "https://example.com/page" --json
```

注意：GitHub 域会被 Jina Reader 拒（403）——GitHub 内容走 github 渠道。

### Hacker News（社区讨论/技术动态）

```powershell
# 搜索（带 points/comments 热度）
agent-reach collect --channel hacker_news --operation search --input "query" --limit 10 --json
# 榜单
agent-reach collect --channel hacker_news --operation top --input "top" --limit 10 --json
```

### RSS / Atom 源

```powershell
agent-reach collect --channel rss --operation read --input "https://feed-url" --limit 10 --json
```

### MCP 注册表（搜 MCP server）

```powershell
agent-reach collect --channel mcp_registry --operation search --input "query" --limit 10 --json
```

## 输出解读

- `ok: true` = 成功；`error` 非空 = 失败（`retryable` 标记可重试）
- `items[].text` = 正文/摘要；`items[].engagement` = 热度（stars/points）
- `meta.pagination` = 分页信息（`has_more`/`total_available`）
- 大输出可加 `--raw-mode none` 丢弃 raw payload、`--item-text-mode snippet`
  截短正文，减小 token 占用

## 项目内衔接（tpc_compiler）

- 采集结果按 AGENTS.md 范式落档：调研结论写 docs/references.md（定位 → 管线
  结构逐阶段对比 → 亮点标注（🔥直接借鉴/💡启发/📌路线观察）→ 可实现性
  评估）；立项前先落档（先落档后动手）。
- 外部工具调研走 project 相关章节索引（references.md「索引（按类别）」）。

## 安全边界

- 不配置任何登录凭据（twitter-cookies 等一律不碰）
- 只读公开数据；凭据本地存储不存在，无封号风险
- 本 skill 是采集层——排序/总结/落档由调用方（我）完成
