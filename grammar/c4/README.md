# grammar/c4 — Tiny C 演示 DSL（第二语言验证）

## 目的

P0.2 主线（第二语言验证）：验证"语言无关性（核心无渗透）+ forkable 主张"。
Verilog 是"一个已实现语言实例"，本包是第二个实例——跑通后"forkable、不
rewrite"从口号变事实。

## 参照

- `reference/c4/c4.c`（rswier/c4，~500 行最小自举子集 = 最小完备内核）——**范畴裁剪基线**
- chibicc（rui314，commit = 特性增量）——实现节奏参照

## 状态

位置已开，范畴裁剪待定（P0.2 第一步）。开工前定三件事：

1. **范畴裁剪**：c4 内核（int/char/指针/数组/函数/if/while/for/递归）vs 扩展
   （struct/float/switch 等明确不进）——进/不进清单
2. **任务拆分顺序**：lexer → parser → analyzer → transform → renderer 先哪层
3. **核心渗透预检**：先跑最小 lexer 验证，尽早暴露 core 里的 Verilog 渗透

## 结构约定（遵循 grammar/<lang>/）

- `tpc.toml`：语言包入口（[lexer]/[parser]/[renderer]/[linter]/... 声明）——
  范畴裁剪确定后填，避免半成品触发 fail-fast 配置验证
- 规则文件按数字前缀排序（`00_*.toml` / `01_*.toml` ...）
- `base/`：共享 token/lexer/operator 基础
- `plugins/`：语言插件（如有）

## 待办

- [ ] 范畴裁剪清单（进/不进）
- [ ] 核心渗透预检（最小 lexer）
- [ ] tpc.toml 入口
- [ ] 分层实现（每层一个 commit，参照 chibicc 增量）
- [ ] 语言无关性验收（core 无 Verilog 渗透）
- [ ] "从零搭语言" walkthrough 文档（模型可消费性演示）
