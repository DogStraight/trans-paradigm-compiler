# checks/ — 检查插件族（verilog 语义 / 命名 / 风格检查）

> 引擎机制：检查 = analyzer postpass 钩子 / analyzer 原语 / L1 声明式 `[[checks]]`
> 规则表（见 `.agents/skills/checker-rule-authoring/SKILL.md` 双路径）。诊断
> code/severity/range 协议与 `--json` 输出见 `main.py::_cmd_check` + `analyzer/
> checker.py`（LSP 兼容序列化）；豁免注释语法见 `analyzer/suppress.py` docstring。
> 本表 = 每个 check 插件负责什么 + 各自诊断 code 的就近权威（code 全集按插件索引）。

## 插件清单（每 check 负责的部分）

| 插件 | 机制 | 负责 | 诊断 code |
|------|------|------|-----------|
| `name_check/` | L1 声明式 `[[checks]]`（naming.toml）+ L2 handler（`_filename_check.py`） | 命名约定：module/实例/wire/reg/端口/parameter/localparam/genvar/函数/任务 小写或大写蛇形；NC011 模块名-文件名一致 | NC001-NC011 |
| `width_check/` | postpass | 位宽一致性：赋值/端口连接截断（W201）、位选越界（W202） | W201, W202 |
| `inst_check/` | postpass（跨文件 ProjectChecker 联动） | 模块实例化：定义存在（W101）、端口连接名存在（W102）、参数覆盖名存在（W103）、悬空端口（W104）、多驱动（W105）、inout 非 tri（W106）、字面量连接参数化宽度端口（WC001） | W101-W106, WC001 |
| `latch_check/` | postpass | 锁存风险（条件不全/case 分支推断锁存） | LC001 |
| `unused_check/` | postpass | 未使用声明 | UN001 |
| `case_check/` | postpass | case 完整性 | CC001 |
| `always_check/` | postpass | always 写法风格（组合/时序过程赋值形态） | AW001, AW002 |
| `hier_check/` | postpass（服务型） | 层次引用解析（供其它检查用，无自身诊断） | — |
| `semantic_check/` | analyzer 原语 | 通用名称/引用解析（`check_name_call` 等基础，W001/W002 由 analyzer 基础 primitives 发） | （analyzer 基础） |

> **组件内检查（非 checks/ 族）**：`../typed_ports/_check.py`（增强
> 语法语义良构，恒开 error 阻断展开）——A 表述完整 TP001-004/006、B 连接正确
> TP010-012、C 单驱动 TP020。code 权威在 typed_ports 组件（增强语法语义契约，
> 不是通用 Verilog 检查族，故不落 checks/）。

> 新增 check：在 `checks/` 下建插件目录 + 按 SKILL 双路径实现，code 登记进
> 本表（诊断 code 就近权威）。分类容器（本目录下的子目录）不要求
> 每插件独立成目录——纯规则组件（`rules/`）随位置任意深度。
