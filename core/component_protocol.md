# 组件协议（插件层）

> 文档目的：说明插件层协议——`@register_plugin` / transform 钩子 / analyzer 原语 /
> setup_grammar 组件加载。插件作者（含模型辅助）写 Python 插件靠它，避免从既有插件猜协议。
> 来源：2026-08-13 P2.0 文档化。

## 1. 组件 = 语言包扩展单元

组件（component）是"语法文件 + analyzer 处理器 + transform 处理器"的捆绑包，
通过 `<component>/tpc.toml` 声明，挂在语言包的 `[plugins] enabled` 下。

```
grammar/verilog/plugins/
├── typed_ports/
│   ├── tpc.toml          ← 组件元数据（声明语法文件/处理器/原语）
│   ├── 00_type_decl.toml ← 语法规则（注入点 @ModuleItem 等）
│   └── _transform.py     ← Python 处理器（transform 槽位）
├── formatter/
│   └── ...
└── attributes/
```

**tpc.toml 结构**：

```toml
# grammar/verilog/plugins/typed_ports/tpc.toml
[lexer]
token_ext = { file = "_token_ext.toml", required = false }

[grammar]
files = ["00_type_decl.toml", "06_typed_decl.toml", "10_impl_binding.toml"]

[analyzer]
handlers = ["_mapping.py"]   # mapping_entries（SemanticMappingPlugin 消费）
# analyzer 原语/处理器 = 通用协议：引擎内置原语（scope/symbol/identifier）由
# 规则级 config 键触发；自定义原语/检查按 primitives 列表或同名键触发；组件加工
# 经 postpass 递归展开（typed_ports _expand_ports 先例，写 resolved_ports）

[transform]
handlers = ["_transform.py"]          # 槽位 handler（@register_transform_slot）

[transform.ctx_channels]              # 槽位 ctx 通道：引擎按声明从 scope 派生
# type_map = { symbol_kind = "typed_port", attr = "type_name" }

[[transform.slots]]                   # 槽位触发契约（触发/遍历/ctx/结果接回）
# name/on/walk/result/ctx —— 见 §3

# 编排调度（schedule.py，pipeline_stages.md）：检查 pass + 命名 schedule
[[pipeline.pass]]
name = "post_check"
kind = "check"                # analyze | transform | check
handler = "_check.py:run"     # check 必需；签名 fn(state) -> None

[[pipeline.schedule]]
name = "transform_first"      # 调用方 schedule="transform_first" 启用
passes = [
  { name = "transform", order = 1 },
  { name = "analyze" },
  { name = "post_check", after = "transform" },
]

# 能力声明（P2.5 插件回调能力化）：引擎按能力名查找，不直接 import
# grammar.<lang> 插件。入口 = file.py:fn（fn 返回插件定义的能力 API 面，
# 如 dict 聚合多个函数）。未声明时引擎 get_capability 返回 None（降级）；
# 按语言包限定时用 get_capability_in(name, rules_dir)（只有该语言包
# plugins/ 下的组件才有资格应答——预处理器/渲染这类按 rules_dir 工作的
# 消费点用它避开跨语言串用）。
# 纯能力组件（无 grammar/analyzer/transform 声明，如 formatter）也据此被加载。
# （typed_ports 原 transform_callbacks 能力已随旧 analyze 原语链删除，P1.5 step 2）
[capabilities]
formatter = "_capability.py:build_formatter"
# macro_policy = "_policy.py:build_macro_policy"      # 宏处置策略（预处理器问询）

# 渲染插件声明（覆盖式输出）：语言包 tpc.toml [plugins].render = "组件名"
# 启用后，管线渲染阶段直接调用 handler 产出最终文本（如 c4 汇编），跳过
# 主管线源端渲染——输出唯一性，覆盖式（与 analyze/transform 的叠加式不同）。
# handler 签名：fn(ast, ctx) -> str（ctx 提供 log 等）。未声明 = 主管线源端渲染。
[render]
handler = "_asm.py:render_asm"
```

能力 fn 返回的 dict 就是**引擎↔语言包的 API 面**：键名即契约，故键名必须**语言中性**
——引擎不按名去调用"某个语言的具体步骤"。现存能力面的约定：

| 能力 | 引擎消费的键 |
|---|---|
| `formatter` | `BoundaryScanner`（扫描器）、`build_engine`（pass 引擎）、`pre_scan_passes`（**扫描前的前置文本遍列表**，按声明序；语言包决定有几遍、叫什么——引擎不知道每遍的语义，缺省 = 不跑） |
| `macro_policy` | `plan`（宏调用点事实 → 处置方案；见 `preprocessor/macro_policy.py`） |

## 1b. 精化器能力位（`elaborator`）

> 引擎侧实现：`analyzer/elaboration/`（机制与职责见其 `README.md`）；插件示例：
> `grammar/verilog/plugins/elaboration/`。
> 为什么这样切：引擎若持有端口/参数/信号图/连接这些**语言形状**，就会随语言增删而改
> ——把"最小可视单位"压到**文件**，语言知识只剩插件一处落点（权衡过程见 git log）。

**引擎只做文件操作**（读源 / 宏展开 / 解析 / AST 缓存 / 行映射与宏区间 / 依赖发现编排）；
"世界由哪些事实构成"（端口有宽度、参数有值文本、信号有驱动/负载、generate 怎么判）是
**语言知识** → 由语言包经此能力位声明成一张**可扩展的项列表**，引擎按列表驱动
「定位 → 求解 → 归位 → 核验」（与 §1 的 `formatter` / `macro_policy` 同款能力机制）。

```toml
[capabilities]
elaborator = "_elaborator.py:build_elaborator"
```

入口返回 `{"items": [...], "solvers": {...}}`；项字段：

| 字段 | 必/选 | 含义 |
|---|---|---|
| `name` | 必需 | 项目名（容器键前缀；语言包作用域内唯一） |
| `scope` | 必需 | 执行原子：`file` / `unit` / `project`（**引擎定义枚举**，机制面） |
| `solver` | 必需 | **求解函数名**（加载期从 `solvers` 解析；缺失 → fail-fast） |
| `provides` | 必需 | 本项负责的**容器键**（非空、**跨项唯一**） |
| `depends_on` | 可选 | 项间依赖（引擎按**拓扑序**跑；求解器经 `ctx.products` 读前项产物） |
| `locator` | 可选 | **声明式定位**：在 scope 原子子树内按**规则名**收节点 |
| `locator_fn` | 可选 | 定位本身需要算法时的函数名（与 `locator` 二选一） |

`locator` / `locator_fn` **都可省略**（省略 ⇒ 求解器收到 `hits = [原子根]`，自行走子树）
——"怎么找"本身就是语言知识。

- **求解签名** `fn(hits, atom, ctx) -> Mapping | None`：返回本原子为 `provides` 子集贡献的
  「容器键 → 值」；`None` = 本原子无此类值（合法）。`ctx.products` 是容器**活视图**；
  `ctx.service` 是**语言无关服务句柄**（`render` / `files` / `unit_node` / `unit_file`）。
- **产物容器** `context.extra["elaboration"] = {容器键: {原子键: 值}}`——引擎只保证**容器与
  生命周期**，**条目名与值形状由语言包定义**（引擎不解释语义）；原子键冲突**取先**
  （与引擎单元索引"首个定义者优先"同口径）。
- **降级**：未声明该能力 → 不提取、不递归、不注入容器（`tpc check` 退回单文件 lint + analyze）。
- **fail-fast**（全部在**加载期**）：未知键 / 项重名 / 容器键跨项重复 /
  `depends_on` 自引用与成环 / `locator` 与 `locator_fn` 同给 / 求解名未解析 / `scope` 非法。
- **核验只做强方向**：求解器返回**未声明的容器键** → fail；**不**因"声明了但某原子无产物"
  报错（按原子出产物时空是常态）——**与 `pipeline/schedule.py::_verify_produced` 的刻意差异**。
- **引擎角色位已退场**（精化收口时）：曾有 `role` 字段用于"引擎消费插件产物"的寻址
  （条目名由插件定 ⇒ 引擎无法按名寻址自己也要用的产物）。终态下引擎**不消费任何插件产物**，
  故该机制整体删除（`role` 字段 / `ROLES` 枚举 / `role_key`），**不留登记槽**——声明的项
  集合里不再有"引擎自己要用的产物"这类成员。声明 `role` 现在会被"未知键"在加载期拦下。
  将来若确有此需求，按同一契约重新登记；判据：**登记项必须有引擎侧消费方**（终态下没有
  ⇒ 连同登记槽删除），历史过程见 git log。

## 1c. 引擎 vs 插件的能力边界（设计原则）

> 管辖"某能力该放引擎还是插件"的通用原则，适用于精化范围外的待议面（如数字形态、
> analyze→transform 映射通道的契约键名）——动手前先按本节判，仍守"先落档后动手"。

**自带配置的增量设计**：引擎侧留**占位 + 简单实现**（跑通最普适形态），语言特有的完整
实现**集中到语言适配层**——配置复杂度与语言知识都落在插件侧，插件又靠引擎的原语组合而
不必重复造骨架。

- **三选一别走错**：引擎硬编码（禁） / 引擎配置字段（慎） / **插件实现（首选）**。
  "为让引擎普适而设计一套 schema"会把复杂度从代码搬到配置，并为新形态预留表达力缺口。
- **判据**：① *普适性*：去掉所有语言包声明后，引擎的简单实现能否对任意输入给出**可解释**
  结果？能 → 引擎；不能 → 插件。② *配置 vs 代码*：**能被表单穷举、且不涉及算法/状态机/
  语义求值**的少量变体 → 留配置；需要算法/状态机/求解的 → 移插件代码。③ *增量*：插件只写
  "与默认的差"（override / 扩展点），不复制骨架。
- **取舍的定位**：声明式表达一切 ⇒ 配置面无限，不可能。做法是**把"会变动的结构"做成配置，
  把"特异的部分"做成语言包代码**——不是消灭取舍，而是把取舍**局部化**（每个决定只影响一个
  组件、可回滚、可被测试锁住）。看它在语言间的分布来判：

  | 语言间分布 | 归宿 |
  |---|---|
  | 多语言共有、且形态稳定（只有值不同） | **配置**（值走声明） |
  | 多语言共有、且结构一致（形态相同） | **引擎骨架**（上提，避免各语言复制声明） |
  | 单语言特有，或各语言形态各异 | **插件代码**（下沉） |

- **两个可机械测的失效信号（发现"放错了"）**：① *该上提却还在配置*：同一 schema 下多个
  语言包的声明高度相似（复制粘贴式）→ 应上提为骨架/默认；② *该上提却还重复*：同一段逻辑
  出现在 ≥2 个语言包，或插件与引擎默认逐字同体（Bifrost 重复扫描 + 既有结构判据可测）→
  应上提。两条都是**往返通道**：只能单向移动（一味下沉或一味上提）会累积另一种债。
- **普适原语必须共享**（否则各插件重写"跳空白"之类会漂移）：既有 `core/token_protocol`、
  `lexer/lexer_utils`、`core.define.iter_nodes` 已是这类原语，改动时明确清单。
- **配置面膨胀的实证**：`grammar/verilog/base/_number.toml` 用 7 个字段 × 4 个形态块声明
  数字形态、由 `lexer/number_gen.py` 编译成状态表——加形态会撞 schema 表达力边界。
- **诚实代价**：声明式 → 命令式后，**加语言不再是零代码**（c4/yaml 需写一小段插件或继承
  默认）；换来的是引擎 schema 与代码不随语言数增长。
- **既有约束一并遵守**：语言知识零进代码、不留兼容垫片、删除先证后删、配置加载 fail-fast
  （见 `AGENTS.md`「硬约束」与 `policy/doc-alignment.md`）。
- 外部路线参照（GCC 手写前端 + 下游共享、LLVM IR 中间层、语言工作台元语言 + 生成）见
  `docs/references.md`。

## 2. 加载流程（setup_grammar）

```
discover_components(plugins_dir)   # 递归扫描插件目录树的 tpc.toml
  → _resolve_dependencies(metas)   # 按依赖排序（meta 里声明 deps）
  → load_component(meta)           # 逐个：
       grammar_files ← [grammar].files 的 .toml
       analyzer     ← [analyzer].handlers 的 .py（import 执行 @register）
       transform    ← [transform].handlers 的 .py（import 执行 register_plugin）
       pipeline     ← [pipeline] pass/schedule 声明（handler 解析为可调用）
       capabilities ← [capabilities] 能力入口（file.py:fn 解析为可调用，
                      get_capability 按名查找——pipeline 不再直连插件）
       render       ← [render].handler（file.py:fn 解析为可调用，渲染插件
                      覆盖式入口——语言包 [plugins].render 启用后接管渲染）
```

语法文件由 `setup_grammar` 合并进规则树；处理器模块被 import（副作用 = 注册）。

### 聚类目录（用户自定义分类，引擎不规定枚举）

`plugins/` 下**任意深度子目录**均可作为分类容器（如 `plugins/checks/name_check`、
`plugins/syntax/sim`），任何含 tpc.toml 的目录是一个组件；不含 tpc.toml 的
目录只是分类容器被跳过。组件名 = tpc.toml 所在目录的 basename（依赖/配置/
启用列表仍按组件名引用，聚类不改变引用名）。分类名由用户自由组织，引擎
不规定枚举值。重名组件（不同分类下同名）→ fail-fast。

纯规则组件（如 `name_check`：空 tpc.toml + `rules/*.toml`）不是 discover
组件，由 check_registry 递归发现（`rules/` 目录随组件所在位置任意深度）。

**verilog 当前组织（建议性约定，非引擎强制）**：

```
plugins/
├── syntax/        # 纯语法插件（[grammar] files 注入，如 sim/specify/gates…）
├── checks/        # 检查插件（语义检查/postpass/规则表，如 name_check…）
└── <根目录>       # 混合型/增强型插件（语法+语义+变换联动，如 typed_ports）
                   # 与纯能力插件（如 formatter——无语法/分析/变换声明）
```

根目录是**合法且刻意保留**的位置：混合型插件（如 typed_ports，语法增强
牵动 analyzer/transform 多阶段）归任何单一功能类都不准确，留在根目录；
纯能力插件（formatter）同样无单一功能类可归。分类目录是可选组织方式，
引擎不规定枚举，新插件可自由选择根目录或任一分类目录。


## 3. transform 槽位（@register_transform_slot）

```python
# grammar/verilog/plugins/typed_ports/_transform.py
from core.plugin_loader import register_transform_slot
from core.define import Node

@register_transform_slot("build_wrapper")
def build_wrapper(node: Node, ctx) -> Node | None:
    """节点级变换：返回新节点（替换）、None（删除）或原节点（原地改）。"""
    return node
```

- 槽位契约在 tpc.toml `[[transform.slots]]` 声明（槽位 handler 文件在
  `[transform].handlers`）：

```toml
[[transform.slots]]
name = "build_wrapper"          # 槽位名（须与 @register_transform_slot 注册名一致）
on = "TypeDecl"                 # 触发节点名（或名列表）
walk = "top"                    # top（根 sub_node 顶层）/ recursive（整树递归）
result = "extra"                # extra / none / replace（1:1 替换+注释迁移）/ remove
ctx = { type_decl = "$node", impl_block = "TypeImplDecl" }   # $node = 触发节点自身
```

- `ctx` 固有通道：`root_scope`（analyze 产物）自动注入；其余按声明从 scope 树
  派生（**语言知识就地**，引擎不认识 kind/attr 语义）：

```toml
[transform.ctx_channels]
type_map = { symbol_kind = "typed_port", attr = "type_name" }   # {符号名: attrs[attr]}
```

- **时点不在此声明**：归管线配置 `[pipeline.units.*]`（见 pipeline/README.md）。
- **执行 = 引擎 `SlotRunnerPlugin`**（`transform/slot_runner.py`，语言无关）：按
  声明遍历（`walk`）→ 触发（`on`）→ 构造 ctx（声明 + 通道）→ 调 handler →
  按 `result` 接回（`extra` 不接回、handler 自 mark_extra / `none` 原地 /
  `replace` 1:1 替换 + `migrate_comments` / `remove` 从父列表移除）。组件不再需要
  自己的桥插件（typed_ports `_bridge.py` 已删）。加载期 fail-fast：槽位名未注册 /
  `walk`·`result` 取值非法 / `ctx` 形态非法。
- **槽位级单元（5b-3c-3）**：槽位可在管线配置里各自声明时点——
  `[[pipeline.units.<name>]] slot = "<槽位名>"`（与 `impl` 互斥）→ 该单元只跑该
  槽位（`SlotRunnerPlugin(only_slot=...)`）；未声明则整包按声明序跑（现行为）。
- **插件单元实例化参数（5b-3b）**：`impl = "<插件限定名>"` 的单元可带 `params`
  （表）= 插件**构造器关键字参数**覆写（同一插件可多实例）；签名不匹配加载期
  fail-fast。槽位/内置/handler 单元不支持 `params`（声明即 fail-fast）。

## 4. analyzer 原语

```python
# grammar/verilog/plugins/checks/semantic_check/_name_check.py
from core.define import Node
from analyzer.primitives.registry import register

@register("check_name_call")
def check_name_call(analyzer, node: Node, config: dict) -> None:
    """签名固定：analyzer（遍历器）/ node（当前 AST 节点）/ config（规则 analyzer 配置）"""
    self_cfg = config.get("check_name_call") or {}
    ...
```

- 处理器文件在 `[analyzer].handlers`（import 即触发 `@register`）。
- 原语在规则上**按配置键触发**——规则 analyzer 段出现 `原语名 = {...}` 即触发该
  原语并携带配置（键名 = 原语名，一个键同时管触发与配置）：

```toml
# 给主包规则加 analyzer 配置（直接在原文件加字段，无需重声明规则）
[SubroutineCall.analyzer]
check_name_call = { name_attr = "callee" }
```

  （兼容旧写法：`primitives = ["原语名"]` 列表 + 单独配置段，两者合并去重。）

- 内置原语（symbol_declare / scope_enter / scope_exit / identifier_resolve）由固定
  键触发：`symbol` / `scope` / `identifier_ref`。其中 `symbol_declare` 无显式
  `symbol` 时从 `scope` 推断（scope 带 `name_attr` 即视为"声明符号 + 进入作用域"，
  声明规则无需重复写 symbol 配置）。
- 纯 analyzer 插件（只做语义检查、无语法/变换）可只声明 `[analyzer]` 段——组件
  判定已支持（无 `[grammar] files` / `[transform] handlers` 也可加载）。

## 5. TransformPlugin（注册到 AstTransformer 管线）

```python
# transform/config_driven.py（参考）
from transform.engine import register_plugin, TransformPlugin

@register_plugin
class ConfigDrivenTransform(TransformPlugin):
    """配置驱动变换：读规则 TOML 的 [RuleName.transform] 段执行 expand/emit 等。"""
```

- `@register_plugin` 注册到 AstTransformer 的插件表，`transform` 阶段自动执行。
- 插件经 `AstTransformer.set_shared("rules", ...)` 共享上下文。

## 6. 语法注入（inject）

```
[TypedPortDecl.inject]
targets = ["@AnsiPortDecl", "@ModuleItem"]
```

组件语法通过 `inject` 挂到基础语法的注入点（`@Xxx` 引用位），
`setup_grammar` 把组件规则并入注入点——不修改基础语法文件。

## 7. 数据流（analyzer → transform 通道）

```
TOML grammar rules
      ↓ (setup_grammar 加载)
Parser 产出 AST
      ↓
Analyzer 遍历 AST，执行组件原语
      ↓ (原语写入 sym.attrs，键见 _protocol.py)
SemanticMappingPlugin 读作用域树，构建映射表
      ↓ (表：type_ports_flat 等)
ConfigDrivenTransform 消费映射表
      ↓ (expand / replace / delete 操作)
Renderer 产出格式化输出
```

### 语义映射数据通道（analyze → transform）

- analyze 侧：组件 postpass 在 scope 完整后递归展开语义数据，写符号自有键
  （如 typed_ports `resolved_ports` = [{direction,name,packed_range}]）
- transform 侧：SemanticMappingPlugin 读 `sym.attrs`（mapping_entries 的
  source.attr）建 `type_ports_flat` 表，ConfigDrivenTransform 消费展开
- 历史：曾有过 `resolve_refs` 原语 → `_ref_callbacks` → `_semantic_mapping`
  `_apply_refs` 的回调通道（typed_ports 旧机制）；P1.5 step 2 已整体移除
  （analyze 后置 postpass 递归展开替代），不再使用——别走回头路

所有此类魔数键集中在 `core/_protocol.py` 定义，**禁止在代码里写裸字符串**。

## 8. 写新组件的最小步骤

1. `plugins/<name>/tpc.toml`：声明语法文件 + 处理器 + 槽位/原语。
2. `plugins/<name>/00_xxx.toml`：语法规则（`inject` 挂到基础语法）。
3. `plugins/<name>/_handler.py`：Python 处理器（`@register_plugin` / `@register_transform_slot` / `register_primitive`）。
4. 语言包 tpc.toml `[plugins] enabled = ["<name>", ...]` 挂载。
5. `setup_grammar` 自动发现加载；`get_component_grammar_files` 取语法文件。

## 9. 常见坑

| 坑 | 现象 | 修法 |
|---|---|---|
| 处理器模块未 import | 槽位/原语未注册 | `[analyzer].handlers` / `[transform].handlers` 列出 |
| inject target 拼错 | 语法未挂上 | 确认注入点存在（`@Xxx` 引用位） |
| 原语顺序错 | analyzer 阶段顺序乱 | `[analyzer].primitives` 数组顺序 |
| 单语言污染 | 组件跨语言加载 | tpc.toml 声明 `lang` 过滤 |
| 魔数键裸写 | 拼写错难查 | 用 `core/_protocol.py` 常量 |
