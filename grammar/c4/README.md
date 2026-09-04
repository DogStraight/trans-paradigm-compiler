# grammar/c4 — Tiny C 演示 DSL（第二语言验证）

## 目的

P0.2 主线（第二语言验证）：验证"语言无关性（核心无渗透）+ forkable 主张"。
Verilog 是"一个已实现语言实例"，本包是第二个实例——跑通后"forkable、不
rewrite"从口号变事实。

**定位（2026-08-29 战略更新）**：语言包主体收敛为 verilog2005 + C23；c4
是第二语言验证 + "从零搭语言"模板 + **C 核心语法的管线支持子集**——C23
立项时可作核心子集起步（c4 范畴 + 常用面），但 c4 **≠ C23**：完整 C
（ISO/IEC 9899:2024）是数量级更大的工程（见 ROADMAP「C23 语言包」）。

## 参照

- [`rswier/c4`](https://github.com/rswier/c4) 的 `c4.c`（~500 行最小自举子集 = 最小完备内核）——**范畴裁剪基线**
- chibicc（rui314，commit = 特性增量）——实现节奏参照

> **署名**：本语言包对齐 `rswier/c4`（[MIT License](https://github.com/rswier/c4/blob/master/LICENSE)）
> 的 `c4.c` 行为（词法/表达式/语句/指令集）。仅参考行为与指令集设计，
> 未复制其源码；c4.c 版权归其作者所有。

## 状态

范畴：**完整实现**（本体不大，不裁剪）——覆盖 c4 全量：
类型（char/int/指针）、字面量（十/十六/八进制、字符、字符串）、
if/else、while、return、块、表达式语句、全局/局部声明、函数、enum。

**产出决策（2026-08-11）**：不做"还原 C 代码"的 renderer，而是**生成 c4 VM
指令集汇编**（LEA/IMM/JMP/ADD/...，c4.c 的 opcodes）——c4 本身是编译器，
产出代码更有意义，且指令集简单（c4.c 有现成编译逻辑参考）。

**架构约束（2026-08-12）**：**单语言选择模型**——管线一次只使用一种语言的
语法，不混合多种语言配置；`ConfigRegistry.load_language` 定位为"初始化时选
一个语言包"（非运行中热重载，切换 = 重新初始化）。语言热重载需求后置。

实现进度（每阶段验证后勾选）：

- [x] **词法层**（阶段 1-2）：token/lexer/关键字配置 + C 代码 tokenize 验证
- [x] **表达式层**（阶段 3）：原子 + Pratt 全运算符（赋值/逻辑/一元/调用/下标/
      类型转换/条件/自增/sizeof/解引用 12 种全 parse 正确）
- [x] **语句/声明层**（阶段 4）：if/else、while、return、块、表达式语句、
      变量声明、函数定义、enum——`int main(){...}` 完整程序 parse 成功
- [x] **汇编生成**（阶段 5）：AsmGenPlugin（c4 编译逻辑：符号表/表达式/语句/
      函数 → c4 VM 指令，跳转回填）+ renderer 逐行渲染——`int main(){...}`
      全管线（lex→parse→analyze→transform→render）产出完整汇编，374 回归无破坏
- [x] **渲染插件覆盖式**（2026-08-29）：asm_gen 组件声明 `[render]` handler
      （`_asm.py:render_asm`），c4 tpc.toml `[plugins].render = "asm_gen"` 启用——
      渲染阶段由 handler 直接产出汇编文本（覆盖主管线源端渲染，输出唯一性；
      与 analyze/transform 的叠加式不同）。管线 `_stage_render` 检测到启用即
      跳过源端还原/注释回插/格式化/幂等（中间表示无源端语义）。
- [x] **测试样本 + 组件加载接入 + 验收**（阶段 6）：
      - 组件加载参数化（plugin_loader 支持按语言包扫 plugins/，setup_grammar
        清空并加载当前语言包组件——单语言不混合；handler 幂等加载）
      - tests/languages/c4/test_c4_asm.py：6 项集成测试（赋值/if-else/while 回跳/调用/
        优先级/守卫），用独立 GrammarRulesRegister 实例避免污染全局单例
      - 修复第二个语言差异：语句 end_case=[newline]（Verilog 换行定界）→ C 以
        ;/} 定界——单行多语句解析失败
      - 全量 380 通过（374 + 6）

## 剩余/后续
- 语言无关性验收文档化（已修复 5 个核心渗透/单语言假设，见下）
- "从零搭语言" walkthrough 文档（模型可消费性演示）

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

## 定位：最小语言包模板（2026-08-13）

c4 是**模型/开发者"从零搭新语言"的起步模板**：
- 最小完整语言包（token → lexer → 表达式 → 语句/声明 → transform → 汇编渲染）
- 覆盖语言无关管线的每一层（lexer/parser/analyzer/transform/renderer）
- 含一个完整插件（AsmGenPlugin，演示 @register_plugin 协议）

**从 c4 起步做新语言的路径**：拷贝 grammar/c4/ → 改 token/关键字/规则 → 增量加
语言特性（参照 chibicc 特性增量节奏）。相比从零写，省掉"管线怎么分层/每层写什么"
的摸索——照 c4 的结构填内容即可。

配套文档：
- docs/language_walkthrough.md（从零搭语言逐层指南）
- core/component_protocol.md（插件层协议）
- parser/expression_conventions.md（表达式隐式约定）
- core/config_lifecycle.md（配置生命周期时序）

## 待办

- [x] 核心渗透预检（最小 lexer）
- [x] 表达式/语句/声明规则
- [x] 汇编生成（transform 插件 + renderer 布局）
- [x] 测试样本 + 管线跑通
- [x] 语言无关性验收（core 无 Verilog 渗透）
- [x] "从零搭语言" walkthrough 文档（docs/language_walkthrough.md）
