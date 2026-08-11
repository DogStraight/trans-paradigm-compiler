# grammar/c4 — Tiny C 演示 DSL（第二语言验证）

## 目的

P0.2 主线（第二语言验证）：验证"语言无关性（核心无渗透）+ forkable 主张"。
Verilog 是"一个已实现语言实例"，本包是第二个实例——跑通后"forkable、不
rewrite"从口号变事实。

## 参照

- `reference/c4/c4.c`（rswier/c4，~500 行最小自举子集 = 最小完备内核）——**范畴裁剪基线**
- chibicc（rui314，commit = 特性增量）——实现节奏参照

## 状态

范畴：**完整实现**（用户定：本体不大，不裁剪）——覆盖 c4 全量：
类型（char/int/指针）、字面量（十/十六/八进制、字符、字符串）、
if/else、while、return、块、表达式语句、全局/局部声明、函数、enum。

实现进度（每阶段验证后勾选）：

- [x] **词法层**（阶段 1-2）：token/lexer/关键字配置 + C 代码 tokenize 验证
      - `tpc.toml` [lexer] + `base/_token.toml` + `base/_lexer.toml` + `token.toml`
      - 验证通过：`int main(){ printf("hello\n"); int x=0x1F; char c='a'; ... }`
        → 关键字/标识符/十/十六进制数字/字符/字符串/运算符/注释(// #) 全对
      - **机制依赖**：`ConfigRegistry.load_language(rules_dir)`（core/config_registry.py）
        从指定语言包重新声明并加载——打破"import 期只注册默认包"的单语言假设
- [ ] 表达式规则（阶段 3）：原子 + Pratt 全运算符链
- [ ] 语句/声明规则（阶段 4）：if/else、while、return、函数、变量、enum
- [ ] analyzer 符号表 + renderer（阶段 5）
- [ ] 测试样本 + 管线跑通 + 语言无关性验收（阶段 6）

## 结构约定（遵循 grammar/<lang>/）

- `tpc.toml`：语言包入口（[lexer]/[parser]/[renderer]/[linter]/... 声明）
- 规则文件按数字前缀排序（`00_*.toml` / `01_*.toml` ...）
- `base/`：共享 token/lexer/operator 基础
- `plugins/`：语言插件（如有）

## 待办

- [x] 核心渗透预检（最小 lexer）——词法层跑通，未发现 core 渗透
- [x] tpc.toml 入口
- [ ] 表达式/语句/声明规则
- [ ] analyzer 符号表 + renderer
- [ ] 测试样本 + 管线跑通
- [ ] 语言无关性验收（core 无 Verilog 渗透）
- [ ] "从零搭语言" walkthrough 文档（模型可消费性演示）
