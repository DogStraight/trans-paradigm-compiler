# 语义检查插槽架构（semantic checks）

> 本文件 = 语义检查插槽"怎么拼"（机制权威）。决策依据：2026-08 前置调研
> （references.md「静态检查器功能调研」）+ 分阶段落地演进（P1-P4 + 跨文件，
> 见 §10；原 ADR-0004/0005 已归档，历史 git log 追）。
> 状态：**P1 机制层 + P2 窄版 + 跨文件联动 + P3 声明式规则表 + P4 用户配置层
> + L1 注释驱动测试已落地**（2026-08-25 P1/P2/P2.5；2026-08-28 P3/P4/L1 测试）。

## 1. 定位与边界

analyzer 阶段（符号表已建立）的语义检查插槽。**只做三件事**：

1. **配置敏感类检查**——tpc 独有：宽度/参数是配置化的，检查"字面量 vs 符号量"的脆弱匹配。
2. **链级溯源**——HDL 领域空白：报告带赋值链（CodeQL path-problem 式）。
3. **声明式规则机制**——用户"配置优先、脚本兜底"的自定义层。

**不做**（Verilator 已覆盖，不重造）：宽度截断/未连接/未使用/锁存器/case 完整性等。

## 2. 架构总览

```
analyzer 遍历（原语按 [RuleName.analyzer] 触发）       ← 已有（check_name_call 范式）
   │
   ├─ L1 声明层：TOML [[checks]] 规则（规则=数据）       ← 已实现（P3）
   │        └─ 用户配置层：config/tpc_config.json checks 段 ← 已实现（P4）
   ├─ L2 脚本层：@register 原语 / handler 模块          ← 已有机制（semantic_check 插件）
   │
   └─ post-pass 钩子（遍历收集 → 结束后链式走查）        ← 已实现（P1，mechanism）
          │
          └─ 统一报告管道（Diagnostic + related 链）     ← 已实现（P1）
                └─ 跨文件联动（ProjectChecker 注入
                    module_index / inst_sites）          ← 已实现（inst_check
                    插件：W101/W102/W103/WC001）
```

## 3. 规则声明 schema（L1+L2 合一）✅ 已落地（P3，2026-08-28）

规则表 = 语言包插件目录 `rules/*.toml`（`[[checks]]` 数组，规则=数据），
引擎通用执行器（`core/check_registry.py` 加载校验 + `analyzer/checks.py`
遍历后按符号 kind 分发判定）。第一个自定义示例：
`grammar/verilog/plugins/checks/name_check/rules/naming.toml`（NC001-NC010，
svlint naming 族蓝本）。

```toml
# grammar/verilog/plugins/checks/name_check/rules/naming.toml
[[checks]]
id = "NC001"
category = "naming"
severity = "warning"
scope = ["rtl", "tb"]
kind = "module"                    # 分发键：符号种类（module/wire/reg/port/…）
message = "module 名 '{name}' 不符合小写下划线约定（{pattern}）"
pattern = "^[a-z][a-z0-9_]*$"      # 声明式判定：正则匹配符号名
# handler = "_h.py:check_no_t_suffix"  # L2 脚本兜底（可选，复杂判定）
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 全局唯一（前缀=分类，如 NC=naming check） |
| `category` | str | 分类：width / naming / race / cdc / style… |
| `severity` | enum | error / warning / info |
| `scope` | list | 适用作用域；与用户配置 per_file 叠加（P4） |
| `kind` | str | **分发键**：符号种类（module/wire/reg/port/parameter/function/task/module_instance/genvar…，对应语法 TOML `[*.analyzer.symbol] kind`） |
| `message` | str | 模板，`{var}` 插值（name/kind/pattern/id/severity） |
| `pattern` | str | 声明式判定：正则匹配符号名；缺省 = 仅靠 kind 分发（handler 兜底） |
| `handler` | str | L2 脚本实现引用 `模块:函数`（`file.py:fn`，fn(symbol, rule, context) -> str\|None）；缺省 = 纯声明式 |

执行器（`analyzer/checks.py::check_rules_pass`，零语言知识）：
遍历后对 `analyzer.all_symbols` 按 `sym.kind` 查规则表（kind 分发），
`re.match(pattern, sym.name)` 判定；不匹配 → `context.report(message
插值, code=id, level=severity, node=sym.decl_node)`。handler 兜底：
pattern 缺省或判定不足时调用脚本（返回 str = 诊断消息，None = 通过）。
规则表加载（`core/check_registry.py`）fail-fast：id 重复 / severity
非法 / pattern 非法正则 / kind 缺失 / handler 模块缺失 → 直接报错
（ADR-0003）。

## 4. 用户配置层（`config/tpc_config.json` 的 checks 段）✅ 已实现（P4，2026-08-28）

> 设计文档原文是 `tpc.toml [checks]`；实现适配项目实际用户配置形态
> （core/_user_config.py 定位的 `config/tpc_config.json`，JSON）。

```json
{
  "checks": {
    "enabled": ["NC001", "NC005"],
    "overrides": { "NC001": { "severity": "error" } },
    "per_file": { "tb/*.sv": { "disabled": ["NC001"] } }
  }
}
```

- `enabled`：未列出 = 关闭（Semgrep"不选即关"）；缺省（无 checks 段或
  无 enabled）→ 全部规则启用（向后兼容 P3 行为）。
- `overrides`：severity 提升/降级（ESLint off/warn/error 式）——提升到
  error 后 `tpc check` exit_code 变 1（门禁生效）。
- `per_file`：文件 glob 豁免（Ruff per-file-ignores 式）——`tb/*.sv` /
  `**/tb_*.v` 尾部匹配（pathlib.PurePath.match 语义），符号文件来自
  ProjectChecker 注入的 `node._file`；单文件 analyze 无文件上下文时不参与。
- 诚实边界：测试台死值是**故意的**（测固定宽度），默认 TB 豁免由用户配置决定，不内置假设。
- 配置加载沿用 fail-fast（ADR-0003）：enabled/overrides/per_file 引用
  不存在的规则 id、severity 非法 → 直接报错，不静默降级。
- 实现：`core/check_registry.py::load_user_check_config`（读取 + 校验，
  按配置路径缓存）+ `analyzer/checks.py::check_rules_pass`（执行时应用：
  enabled 过滤 / severity 覆盖 / per_file 豁免）。

## 5. post-pass 钩子协议（机制核心）✅ 已实现（P1）

现有原语节点锚定，链式检查需要跨节点分析。协议：

```toml
# 插件 tpc.toml
[analyzer]
primitives = ["collect_width_src"]     # 遍历期收集（节点锚定，L2 原语）
postpasses = ["_chain_walk.py:run"]    # 遍历后走查（已实现）
```

```python
# _chain_walk.py
def run(analyzer, context) -> None:
    """遍历结束后调用：访问 analyzer.all_symbols / context.extra 中已收集的
    端口、赋值链；沿链走查，向 context.report 报带 related 的诊断。"""
    ...
```

- 实现位置：`analyzer/traversal.py::AnalysisTraversal._run_postpasses`——
  `analyze()` 的 `_walk()` 之后、`_resolve_pending()` 之后执行。
- 声明解析：`core/plugin_loader.py::_load_postpasses`（`file.py:fn` 格式，
  fail-fast：模块/函数缺失直接报错）+ `get_analyzer_postpasses()` 合并。
- 组件判定：`_parse_component_toml` 将 `[analyzer] postpasses` 计入
  组件标志（纯 postpass 插件如 inst_check 不因无 handlers 被丢弃）。
- 收集阶段沿用现有原语副作用模式（`context.extra` 传递临时状态）。
- **跨文件扩展**（ADR-0005）：ProjectChecker 在 analyze() 前把
  `module_index`（全工程模块表）/`inst_sites`（本文件实例化点）写入
  `AnalysisTraversal._external_extra`，analyze() 合并进 context.extra——
  插件 postpass 可直接做跨文件联动比对。

### 5.1 何时上 postpass（vs 遍历期原语）——时序决策

postpass 在 analyze 遍历结束后跑（scope 树全量、符号全声明），是"需要查完整
scope 再决策"逻辑的**权威时机**。判断标准一句：

> 逻辑是否依赖"遍历还没遇到的符号"？依赖 → 上 postpass（或声明式 checks），
> 不要放遍历期原语。

遍历期自定义原语（`@register` + 规则级 `primitives` 列表 / 配置同名键）只在
走到该节点时跑一次，单遍 DFS 无 deferral——遍历期"回头查别的 type/role 符号"
必然撞后置定义/无回调（typed_ports invert 的 L3 缺陷即此根因，2026-09-08
修复为 postpass 递归展开）。postpass 用途两类：**检查**（§5 主体，报诊断）与
**语义数据产出**（写 `sym.attrs` 供下游消费，见 5.3）。

`tpc.toml [analyzer] postpasses` 列表**有序**——依赖上游产出的 postpass 须排在
其后（typed_ports 的 `_expand_ports` 先于 `_check`，check 读 expander 数据）。

### 5.2 原语触发与配置层级

- **原语触发只认规则级** `[RuleName.analyzer]`（`config.get("primitives")`）。
- 引擎标准原语（scope_enter/scope_exit/symbol_declare/identifier_resolve）由
  **配置键存在**触发（`traversal._is_primitive_triggered` 特判），不走 primitives
  列表；primitives 列表只触发"引擎不认识的自定义原语"。
- 自定义原语两种写法等价：`primitives = ["foo"]` + 独立 `[foo]` 段，或配置里
  直接同名键 `foo = {...}`（键即原语名且触发）。
- 组件级 `tpc.toml [analyzer]` 只放 handlers/postpasses/primitive_order；
  **组件级 `primitives` 无消费者**（曾误写，2026-09-08 删）——别写回去。
- 符号声明时序：`symbol_declare` 在遍历序里先于 `scope_enter`，role 符号落在
  type 父作用域（非自己的子作用域）——遍历期想从子作用域向上查会踩。

### 5.3 sym.attrs 黑板：postpass 产出结构化数据供下游

`sym.attrs` 跨阶段存活（analyze 写、transform 读），是组件自己的黑板。范式：
组件 postpass 从 raw 捕获（如 `symbol_declare` 的 `capture.ports`）递归展开出
**结构化结果写自有键**，下游（组件 `_check`/`_transform`、引擎
`_semantic_mapping._apply_entry`）统一读该键。typed_ports `_expand_ports`
先例：role 端口集（nested + invert 对侧）→ `sym.attrs["resolved_ports"]`
= [{direction, name, packed_range}]；引擎只做通用判断（`attr=="ports"` 且有
resolved_ports），语言语义全在组件。

**删中间层/兜底的安全前提**：postpass 对健康输入全覆盖，且**无条件写键**
（空展开也写 `[]`）——否则下游被迫留 raw/旧数据回退，双实现漂移回归。

## 6. 符号宽度表示（width 检查基础）

```python
@dataclass
class WidthExpr:
    kind: str          # "literal" | "parameterized" | "derived"
    expr: str          # 原文："16" / "DATA_W" / "DATA_W-1"
    node: Node         # 来源 AST 节点（定位用）
    provenance: str    # 来源：port_decl / assign / concat ...
```

- typed_ports 已带 `packed_range` 一路到 AST，宽度信息现成，`WidthExpr` 在其上抽象。
- 检查规则：`literal` 喂给 `parameterized` 端口 → 可疑（"死值"模式）；`literal` 喂给 `literal` → 正常。

## 7. 链追溯报告（Diagnostic.related）✅ 已实现（P1）

```python
# analyzer/diagnostic.py
class Diagnostic:
    ...
    related: list[tuple[str, Node]]   # [(message, node), ...] — node 可跨文件
```

报告形态：

```
WC001 warning: literal 16'hFFFF feeds parameterized port DATA_OUT (width DATA_W)
  chain: tb/tb_spi.sv:42  assign spi_data = test_word;      ← 常量源头（related[0]）
         tb/tb_spi.sv:45  spi_if.data = spi_data;            ← 中间（related[1]）
         rtl/spi_io.sv:10 input [DATA_W-1:0] DATA_OUT         ← 参数化端口（主位置）
```

- 与 linter 侧 `LintDiagnostic` 的关系：语义检查走 analyzer 的 `Diagnostic` 通道（符号级）；两通道在 CLI/report 出口统一渲染（后续）。

## 8. 统一抑制语法

```
// tpc-disable[WC001]             行内忽略指定规则
// tpc-disable-next-line WC001    下一行忽略
// tpc-disable                     本行全部
// tpc-disable-file WC001         文件级
```

- 声明层与脚本层规则**自动获得**同一套豁免（解析发生在报告出口，不区分规则来源）。
- 注释 token 由 preprocessor/lexer 现有注释识别承接。

## 9. 测试框架（按层）✅ L1 注释驱动已实现（2026-08-28）

- **L1 声明层**：注释驱动测试（Semgrep 式）**已实现**——样例源文件内嵌
  `// ruleid: NC001`（必须命中）/ `// ok: NC001`（不得命中）注释，
  `tests/_check_test.py::run_comment_driven(checker, path)` 运行检查后
  断言命中集合（失败报告：`L{行}: ruleid X 未命中` / `ok X 意外命中`）。
  样例资产 = name_check 插件 `cases/*.sv`（零代码测试：新增样例 = 新增
  断言；规则行为变化时随样例自动更新语义）。测试入口：
  `tests/languages/verilog/test_name_convention.py::TestCommentDrivenCases`。
- **L2 脚本层**：RuleTester 式断言——valid/invalid 用例 + 期望诊断逐字段断言（messageId/level/位置/related 链）。

## 10. 分阶段落地计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 | 机制层：post-pass 钩子 + `Diagnostic.related` + 统一抑制 | 钩子/related **已实现**（2026-08-25）；统一抑制未做（并入 P4） |
| P2 | `width_check` 窄版：参数化端口 + 字面量 + 单链 | **已实现**（WC001，跨文件版见下 P2.5 inst_check） |
| P2.5 | 跨文件联动：递归发现 + 模块表 + inst_check 插件 | **已实现**（W101/W102/W103/WC001 + `tpc check` CLI） |
| P3 | L1 声明式 schema + 注释驱动测试框架 | **已实现**（2026-08-28：check_registry + checks.py + name_check 插件 NC001-NC010，rules/*.toml 规则=数据；注释驱动测试 tests/_check_test.py + cases/ 样例） |
| P4 | 用户配置层 `[checks]` + per_file 豁免 + 统一抑制 | **已实现**（2026-08-28：config/tpc_config.json checks 段——enabled/overrides/per_file，fail-fast 校验；统一抑制由 analyzer/suppress.py 覆盖，声明式规则自动获得豁免） |

> Impl: analyzer/checks.py（声明式执行器）/ core/check_registry.py（规则表加载校验）/
> analyzer/checker.py::ProjectChecker / analyzer/traversal.py /
> analyzer/diagnostic.py / core/plugin_loader.py / parser/_production.py /
> grammar/verilog/plugins/checks/inst_check/ / grammar/verilog/plugins/checks/name_check/ /
> main.py::_cmd_check
> Test: tests/engine/analyzer/test_checker.py / test_diagnostic_related.py /
> tests/languages/verilog/test_name_convention.py
> CLI 验收：`tpc check <file> [--include DIR] [--json]`——语法阶段
> （stage=syntax）+ 语义阶段（stage=semantic），exit 1 按 error 级。

## 11. 编写检查规则：实操在 SKILL，插件清单在 checks/README

本架构文档只述引擎机制（§3 schema / §5 post-pass 协议 / §7 related 链 /
§8 统一抑制 / §9 测试框架）；**加规则/写规则的实操**由两份就近文档承载，
不在此重复：

- 双路径实操（L1 声明式 `[[checks]]` / L2 handler-postpass：目录结构、步骤、
  接口契约、选择判据）→ `.agents/skills/checker-rule-authoring/SKILL.md`
  （模型可加载指令包，随项目发布；本架构 §3/§5 是其机制底稿）。
- 插件清单（每 check 插件负责什么 + 诊断 code 就近权威）→
  `grammar/verilog/plugins/checks/README.md`。
