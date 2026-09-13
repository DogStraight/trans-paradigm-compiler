# checks/ — 检查插件族（verilog 语义 / 命名 / 风格检查）

> 引擎机制：检查 = analyzer postpass 钩子 / analyzer 原语 / L1 声明式 `[[checks]]`
> 规则表（**双路径实操见本文「编写检查规则」节**）。诊断
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

> 新增 check：在 `checks/` 下建插件目录 + 按本文「编写检查规则」节双路径实现，
> code 登记进本表（诊断 code 就近权威）。分类容器（本目录下的子目录）不要求
> 每插件独立成目录——纯规则组件（`rules/`）随位置任意深度。

---

## 编写检查规则（双路径实操）

> 适用：在**已有语言包**上新增或修改检查规则。引擎机制（schema /
> post-pass 协议 / related 链 / 统一抑制 / 测试框架）见
> `analyzer/semantic_checks.md` §3/§5/§7/§8/§9——本文只写**动手流程**。

### 两条路径选择（先读这条）

| 判定复杂度 | 路径 | 理由 |
|---|---|---|
| 单符号名/形态（正则可表达） | **L1 声明式** | 零代码，注释驱动测试免费 |
| 需符号表/跨节点走查 | **L2 handler** | 单符号上下文足够，写一个函数 |
| 需跨文件/全工程联动 | **L2 postpass** | module_index/inst_sites 只在 postpass 可得 |
| 多次遍历/复杂分析 | **L2 postpass + 内部函数化** | 参考 width_check 分层 |

**L1 和 L2 共用同一报告管道**（Diagnostic + related 链 + 统一抑制
`tpc-disable[CODE]`）——规则来源不影响豁免/输出形态。

> **完整可运行范例**：`custom_rules_example/`——两条规则各走一条路径
> （EX001 postpass / EX002 handler），含照抄四步、默认关约定与样本配置，
> 动笔前先读它的 README.md。

### 目录结构

```
grammar/<lang>/plugins/checks/<name>/
├── tpc.toml              # 插件声明（postpasses = ["_x.py:run"] 可选）
├── rules/                # 规则表（[[checks]] 数组，规则=数据）
│   ├── <name>.toml       # L1 声明（或 L2 handler 的 kind 分发）
│   └── _*.py             # L2 脚本（handler / 内部函数）
└── cases/*.sv            # 注释驱动测试样例（// ruleid: X / // ok: X）
```

### L1 声明式规则（操作组合，零代码）

```toml
# grammar/verilog/plugins/checks/name_check/rules/naming.toml
[[checks]]
id = "NC012"                    # 全局唯一，前缀=分类
category = "naming"
severity = "warning"            # error / warning / info
scope = ["rtl", "tb"]
kind = "integer"                # 分发键：符号种类（见下 kind 全集）
message = "integer 名 '{name}' 不符合小写下划线约定（{pattern}）"
pattern = "^[a-z][a-z0-9_]*$"   # 判定操作：正则匹配符号名
# handler = "_x.py:fn"          # L2 兜底（可选，pattern 表达不了时）
```

- **生效机制**：插件目录存在即被 `check_registry` 扫描 `rules/*.toml`；
  `analyzer/checks.py::check_rules_pass` 遍历后按 `sym.kind` 分发、
  `re.match(pattern, name)` 判定、不匹配 → report（message 插值
  `{name}/{kind}/{pattern}/{id}/{severity}`）。**零引擎改动**。
- **kind 全集**（对应语法 TOML `[*.analyzer.symbol] kind`）：
  `module / wire / reg / integer / port / parameter / localparam /
  function / task / module_instance / genvar / type / ...`
- ⚠ **pattern 缺省** = 全符号进 handler（L2 兜底）。

### L2 handler（单符号脚本兜底）

```toml
[[checks]]
id = "NC011"
kind = "module"
handler = "_filename_check.py:check_module_filename"
```

```python
# grammar/verilog/plugins/checks/name_check/rules/_filename_check.py
def check_module_filename(symbol, rule, context) -> str | None:
    """签名：fn(symbol, rule, context) -> str | None。
    返回 str = 诊断消息（完整文本，不走 {var} 插值）；None = 通过。
    symbol：.name / .kind / .decl_node / .scope
    rule：  [[checks]] 规则 dict（可读自定义字段）
    context：.report(msg, code, level, node, related) / .extra（跨文件数据，见下）
    """
    node = getattr(symbol, "decl_node", None)
    fpath = getattr(node, "_file", None)   # ProjectChecker 注入的文件上下文
    if not fpath:
        return None  # 无文件上下文（单文件 analyze）→ 跳过
    ...
    return f"模块名 '{symbol.name}' 与文件名不一致"
```

### L2 postpass（插件级整树/跨文件走查）

```toml
# 插件 tpc.toml
[analyzer]
postpasses = ["_chain_walk.py:run"]    # file.py:fn 格式
```

```python
# grammar/verilog/plugins/checks/inst_check/_inst_check.py
def run(analyzer, context) -> None:
    """签名：fn(analyzer, context) -> None。
    analyzer：遍历后状态（.all_symbols / ._ast）
    context：.report + .extra（module_index / inst_sites / connections /
             signal_graph / output_dirs / input_dirs / inout_dirs）
    """
    root = getattr(analyzer, "_ast", None)
    for node in _iter_nodes(root):     # DFS 整棵 AST
        ...
        context.report(msg, code="W2XX", level="warning",
                       node=node, related=[("定义处", other_node)])
```

### context.extra 键（ProjectChecker 注入，跨文件联动）

| 键 | 内容 | 消费场景 |
|---|---|---|
| `module_index` | {模块名: ModuleInfo（ports/params/node）} | 实例化点 × 模块表比对 |
| `inst_sites` | 本文件实例化点列表 | W101-103/WC001 |
| `connections` | 端口连接展开（层 2） | 未连接端口/多驱动 |
| `signal_graph` | (模块, 信号) → {drivers, loads} | W105 多驱动 |
| `output_dirs` / `input_dirs` / `inout_dirs` | 端口方向值集 | 驱动/负载分类 |

⚠ **单文件 analyze（run_pipeline）无这些键**——postpass 需
`context.extra.get(...) or {}` 防御（inst_check 先例）。

### 验证

```bash
python -m pytest tests/engine/analyzer/test_checker.py -q   # L2 断言式
python -m pytest tests/e2e/test_check_accuracy.py -q        # L1 注释驱动门禁
python -m pytest tests/ -q -n auto                          # 全量
python tests/e2e/eval_benchmark.py --oracle=verilator       # 对拍（新规则必跑）
python policy/check_hardcode.py                             # 语言知识不进代码门禁
```

- **新规则必须过“零误报/零漏报”量化评估**（真实语料 7 工程 + 评测集）
  ——过不了按处置三选落地：修 / 降级 / 记录已知边界（AGENTS.md）。
- **语言知识不进代码**：规则名/token/形态全在 TOML/插件层；引擎
  `analyzer/checks.py`、`core/check_registry.py` 零语言知识。
- 跑完 `git add -A && git commit`（只本地提交，不推送）。

### 常见场景速查

| 场景 | 路径 | 蓝本插件 |
|---|---|---|
| 命名/风格检查 | L1（pattern 正则） | name_check（NC001-010） |
| 文件名一致性 | L2 handler | name_check（NC011，_filename_check.py） |
| 跨文件端口连接 | L2 postpass | inst_check（W101-103/WC001） |
| 位宽/截断 | L2 postpass | width_check（W201/W202，最大最全） |
| 锁存/控制流 | L2 postpass | latch_check（LC001） |
| 多驱动 | L2 postpass + signal_graph | inst_check（W105） |
| 纯服务（无报告） | L2 postpass | hier_check（被 width_check 回调） |

### 常见坑（实测教训，2026-08-31）

- **新规则与既有规则 pattern 冲突**：同 kind 的多条规则 pattern 可能互斥
  （实测：NC006 参数“大写下划线” pattern `^_?[A-Z][A-Z0-9_]*$` 与新增
  “`_p` 后缀”规则冲突——`_p` 的小写字母使大写 pattern 违规，两条规则
  对同一符号互报）。加规则前**先 grep 该 kind 既有规则**，确认 pattern/
  语义不重叠；重叠时要么合并进既有规则（加字段），要么明确互斥关系。
- **共享后缀 ≠ 互斥后缀**：parameter/localparam 共享 `_p` 时，复用
  check_kind_suffix 的“外来后缀互斥”逻辑会把共享后缀互相误判为外来
  类型。共享后缀的规则要独立 handler（require 语义：只查“是否按本
  kind 后缀命名”，不查外来）。
- **默认开关是数据决策**：误报面大/与既有规则冲突 → `default = false`
  起步（NC/AW 族先例），真实语料量化后按处置三选（修/降级/记录边界）。
