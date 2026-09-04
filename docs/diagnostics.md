# 诊断 code 命名空间（tpc-check / tpc lint）

> tpc-check 当 pylance 用的诊断协议：稳定 code + severity + range（LSP 兼容结构），
> `--json` 机器可读输出；源码内豁免注释见文末（P1.9 第一步，仿 Verilator
> lint_off/lint_on）。来源调研见 `references.md`「Verilog 静态检查工具群」。
>
> 更新：2026-08-25（P1.9 第一步：suppress 注释落地）；2026-08-28
> （NC001-NC010 命名约定登记，声明式规则 P3）

## 诊断协议

每个诊断字段（与 LSP Diagnostic 对齐）：

| 字段 | 说明 |
|------|------|
| `stage` | `syntax`（语法阶段，linter 反向解析器）/ `semantic`（语义阶段，analyzer 插件） |
| `severity` | 1=error / 2=warning / 3=info（LSP 同款数字） |
| `code` | 稳定规则 ID（本页清单） |
| `message` | 人类可读描述 |
| `range` | 源码位置（0-based line/character，与 LSP 一致） |
| `level` | 语义诊断附加（error/warning/info） |
| `related` | 语义诊断附加（相关位置链，ADR-0004） |

输出：`tpc check --json [--pretty]`（exit_code 由剩余诊断重算——豁免后
无 error 级诊断则归 0）。

## 语法阶段（linter 反向解析器）

| code | 阶段 | 含义 |
|------|------|------|
| `phase1-boundary` | P1 | 块/括号边界配对失败（未配对/错配） |
| `undefined-macro` | P0 | 未定义/未展开的宏 token |
| `phase-statement` | P2 | 语句结构与 production 不匹配 |
| `phase-expr` | P2 | 表达式检查失败（pratt/原子） |
| `phase-unrecognized` | P2 | 语句起点无法识别为任何规则 |
| `lexer-error` | - | 词法错误 |
| `parse-error` | check | 整文件解析失败（tpc check 语法阶段兜底） |
| `linter-internal-error` | - | 检查器内部错误（bug 信号，应报 issue） |

## 语义阶段（analyzer 插件）

前缀约定：`E` = error 级、`W` = warning 级、`WC` = 跨文件检查（ADR-0005，
inst_check 插件）、`NC` = 命名约定检查（name_check 插件，声明式规则
[[checks]]，P3）、`W2xx` = 位宽（width_check）、`LC` = 锁存（latch_check）、
`UN` = 未使用（unused_check）、`CC` = case 完整性（case_check）、
`AW` = always 写法风格（always_check，默认关）。code 全集与各插件职责的
按插件索引视图见 `grammar/verilog/plugins/checks/README.md`。

| code | level | 来源 | 含义 |
|------|-------|------|------|
| `E001` | error | analyzer 基础（_symbol） | 重复声明（同作用域同名） |
| `W001` | warning | analyzer 基础（_identifier） | 未解析的标识符引用 |
| `W002` | warning | analyzer 基础（traversal） | 未解析的名称引用 |
| `W101` | warning | inst_check 插件 | 实例化的模块定义未找到（同目录/--include 搜索无果或拼写错误） |
| `W102` | error | inst_check 插件 | 实例化连接了不存在的端口 |
| `W103` | error | inst_check 插件 | 实例化覆盖了不存在的参数 |
| `WC001` | warning | inst_check 插件 | 字面量连接参数化宽度端口（配置变更时可能成为死值） |
| `NC001` | warning | name_check 插件（声明式） | module 名不符合小写下划线约定 |
| `NC002` | warning | name_check 插件（声明式） | 实例名不符合小写下划线约定 |
| `NC003` | warning | name_check 插件（声明式） | wire 名不符合小写下划线约定 |
| `NC004` | warning | name_check 插件（声明式） | reg 名不符合小写下划线约定 |
| `NC005` | warning | name_check 插件（声明式） | 端口名不符合小写下划线约定 |
| `NC006` | warning | name_check 插件（声明式） | parameter 名不符合大写下划线约定 |
| `NC007` | warning | name_check 插件（声明式） | localparam 名不符合大写下划线约定 |
| `NC008` | warning | name_check 插件（声明式） | genvar 名不符合大写下划线约定 |
| `NC009` | warning | name_check 插件（声明式） | 函数名不符合小写下划线约定 |
| `NC010` | warning | name_check 插件（声明式） | 任务名不符合小写下划线约定 |
| `NC011` | warning | name_check 插件（handler 跨文件） | 模块名与文件名不一致（svlint module-filename 蓝本，多模块同文件防御） |
| `W104` | warning | inst_check 插件 | 实例化端口悬空未连接 |
| `W105` | error | inst_check 插件 | 信号被多驱动源驱动（多驱动范式） |
| `W106` | warning | inst_check 插件 | inout 端口数据类型应为 tri（三态总线语义） |
| `W201` | warning | width_check 插件（postpass） | 赋值/端口连接位宽截断 |
| `W202` | error | width_check 插件（postpass） | 位选/下标/切片索引越界（SELRANGE 对标） |
| `LC001` | warning | latch_check 插件（postpass） | 组合逻辑推断锁存（保持路径未全赋值） |
| `UN001` | warning | unused_check 插件（postpass） | 内部信号声明未使用（wire/reg/integer） |
| `CC001` | warning | case_check 插件（postpass） | case 无 default 分支（组合未覆盖全分支） |
| `AW001` | warning | always_check 插件（postpass，默认关） | 时序 always 内阻塞赋值（应非阻塞） |
| `AW002` | warning | always_check 插件（postpass，默认关） | 同 always 块同信号混用阻塞/非阻塞赋值 |

> NC 系列规则声明在 `grammar/verilog/plugins/checks/name_check/rules/naming.toml`
> （`[[checks]]` 规则=数据），severity 可由用户配置
> （`config/tpc_config.json` checks.overrides）覆盖——本表为默认值。
> NC001-NC010 纯声明式（pattern 正则）；NC011 是 handler 兜底形态
> （`_filename_check.py`，读 ProjectChecker 注入的 `node._file` 判定）。
> 规则 id 全集随规则表加载（`core/check_registry.py`），新增规则时同步本表。

## 豁免注释（suppress）

模型生成 v 文本场景：生成器知道自己哪里"故意非标"，在源码内联豁免，
门禁不误伤。仿 Verilator `lint_off`/`lint_on` 注释对：

```verilog
/* tpc-check off W101 */        // 从此行起豁免 W101
ghost_module u ();               // 该处诊断被过滤
/* tpc-check on */              // 此行恢复检查（on 行本身不豁免）

wire x; // tpc-check: disable-line N001   // 仅豁免本行（与违规行同行）
```

- 规则列表为空 = 豁免该处全部诊断；非空 = 仅豁免列出的 code。
- 未闭合的 `off`（无配对 `on`）宽容处理：豁免到文件尾。
- **解析失败的文件不豁免**（parse_error 是坏文件信号，不掩盖）。
- 注意：`/* tpc-check off */` 须在代码区（`//` 之前）——`//` 之后的
  `/* tpc-check off */` 是被注释掉的文本，不构成指令。

## 命名约定（新增检查规则时）

新诊断 code 按 `前缀 + 两位序号`：E/W（+可选 C 跨文件）+ 序号（如 `N001`
命名检查 P1.9）。新 code 必须：① 在此表登记；② 在 suppress 文档说明
适用场景；③ 保持稳定（供 --json 消费方/豁免注释引用）。
