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

**产出决策（2026-08-11）**：不做"还原 C 代码"的 renderer，而是**生成 c4 VM
指令集汇编**（LEA/IMM/JMP/ADD/...，c4.c 的 opcodes）——c4 本身是编译器，
产出代码更有意义，且指令集简单（c4.c 有现成编译逻辑参考）。

实现进度（每阶段验证后勾选）：

- [x] **词法层**（阶段 1-2）：token/lexer/关键字配置 + C 代码 tokenize 验证
- [x] **表达式层**（阶段 3）：原子 + Pratt 全运算符（赋值/逻辑/一元/调用/下标/
      类型转换/条件/自增/sizeof/解引用 12 种全 parse 正确）
- [x] **语句/声明层**（阶段 4）：if/else、while、return、块、表达式语句、
      变量声明、函数定义、enum——`int main(){...}` 完整程序 parse 成功
- [ ] **汇编生成**（阶段 5）：transform 插件（符号表 + 指令发射）→ c4 VM 汇编文本
- [ ] **测试样本 + 管线跑通 + 语言无关性验收**（阶段 6）

**过程中修复的核心渗透（第二语言验证的产出）**：
1. `ConfigRegistry.load_language`（core/config_registry.py）——打破"import 期只注册
   默认包"的单语言假设，同一进程可切换语言包
2. `_glob_match` 通配无匹配不再 fallback 含 * 字面路径（Errno 22）
3. `declare_cfg` 已加载时直接返回真实值（修 load_language 后按需 import 错过 push）
4. `core/define.py` 块边界推导放宽——原硬编码 `keyword.*` 前缀（Verilog 渗透，
   c4 的 `{}` 是 bracket 无法推导致无限递归）→ 任何非 @call 字面 token
5. `parser/rule_selector.py` get_block_rule 优先匿名根块（c4 Program）

## 结构约定（遵循 grammar/<lang>/）

- `tpc.toml`：语言包入口（[lexer]/[parser]/[renderer]/[linter]/... 声明）
- 规则文件按数字前缀排序（`00_*.toml` / `01_*.toml` ...）
- `base/`：共享 token/lexer/operator 基础
- `plugins/`：语言插件（汇编生成插件规划在此）

## 待办

- [x] 核心渗透预检（最小 lexer）
- [x] 表达式/语句/声明规则
- [ ] 汇编生成（transform 插件 + renderer 布局）
- [ ] 测试样本 + 管线跑通
- [ ] 语言无关性验收（core 无 Verilog 渗透）
- [ ] "从零搭语言" walkthrough 文档（模型可消费性演示）
