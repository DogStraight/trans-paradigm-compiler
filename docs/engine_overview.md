# 引擎总览（一条线看懂 tpc 怎么拼）

> 定位：协作方/模型理解引擎的**叙事入口**——从入口到输出跟一条线建立全景，
> 之后想改/查某个子系统再用 `MODEL_INDEX.md` 跳转表。
> 本文件只串**骨架与衔接**（数据形态怎么演化、每站谁负责、为什么这个顺序、
> 去哪深入读），**不复述**各机制文档细节——每站细节走链接，避免与就近机制
> 文档重复（docs 治理 C3 纪律）。
> 读者：想理解"tpc 这个引擎本身怎么转"的人（含零上下文模型）。想学"从零搭
> 一门语言"看 `language_walkthrough.md`，那是另一条线（语言包作者视角）。

## 一句话

tpc 是**配置驱动的语言流水线**：语言知识全部写在 `grammar/` 的 TOML（数据），
引擎是语言无关的通用骨架。输入源代码，经过一条**数据形态逐段演化**的流水线，
产出格式化文本 / lint 诊断 / 跨文件语义检查结果 / 目标代码（c4 汇编）。

## 数据形态主线（记住这条就记住了引擎）

```
源代码(str)
  → 预处理器   宏展开/条件块占位        (str → str)
  → lexer      token 流                (str → list[Token])
  → lint       token 级诊断（拦风格/语法问题）
  → parser     AST（Node 树）          (token → Node)
  → normalize  消 optional/repeat/seq 包装（AST 归一）
  → schedule   编排 pass 序列（analyze/transform/check）
      analyze   作用域/符号/类型 + 语义检查（语义诊断）
      transform 配置驱动变换（语义映射消费）
  → renderer   Doc IR → 文本            (Node → Doc → str，含注释回插)
  → format?    formatter 插件（世界 B pass 管线，可选）
```

各阶段**数据形态**是主线：str → token → AST → 语义结果 → Doc IR → 文本。
阶段顺序的因果很简单——**每站的输入形态是上一站输出的形态要求**：
token 是 token 级 lint 与 parser 的输入，AST 是语义与变换的载体，Doc IR 是
文本布局的可排版中间表示。

## 一次 `tpc format foo.v` 走一遍

| 站 | 数据形态 / 动作 | 负责 | 为什么在这 | 深入读 |
|---|---|---|---|---|
| CLI 入口 | 命令分发（format/lint/check/pipeline/new/config dump） | `main.py` | 从语言包 `tpc.toml [commands]` 读指令声明（指令 = 完整管线默认上的差异项） | `api.md` |
| 配置加载 | 语言包配置解析（fail-fast） | `core/config_registry.py`（declare_cfg 注册制） | 所有阶段行为由配置驱动，先于任何阶段加载 | `core/config_lifecycle.md` |
| 预处理器 | 宏展开 + 条件块占位（str→str） | `preprocessor/`（`_expand.py`/`_reverse.py`/`_bridge.py`） | 宏是文本层机制，先于 token 化处理；反向映射供注释/诊断还原 | `MODEL_INDEX` preprocessor 行 |
| lexer | str → token 流（token/数字形态配置驱动） | `lexer/`（`main_lexer.py` 等） | 词法边界：把源切成 token 再谈结构 | `MODEL_INDEX` lexer 行 |
| 前置 lint | token 级 lint（**反解析器**：复用同一语法 TOML） | `linter/`（scanner/checkers/matcher） | 在 parser 之前用 token 流拦语法/风格问题，尽早报错 | `linter/linter_architecture.md` |
| parser | token → AST（递归下降 + 回溯 + Pratt + 规则选择） | `parser/`（`parser_core.py`/`pratt_parser.py`/`rule_selector.py`） | 语法结构由 grammar 规则数据驱动，非硬编码 | 表达式约定 `parser/expression_conventions.md` |
| normalize | 消除 optional/repeat/seq 包装（AST 归一） | `parser/`（normalizer） | 让后续阶段看到统一节点形态，不感知 TOML 组合写法 | `MODEL_INDEX` parser 行 |
| schedule | 编排 pass：analyze → transform（check 可插） | `pipeline/schedule.py` + `pipeline/__init__.py::run_pipeline_on_source` | analyze 先建语义（作用域/符号），transform 消费语义做变换（顺序因果） | `docs/pipeline_stages.md` + `pipeline/README.md` |
| analyze pass | 作用域/符号/类型 + 语义检查插槽 | `analyzer/`（scope/traversal/checks/primitives） | 跨 token/AST 的语义层 | `analyzer/semantic_checks.md` |
| transform pass | 配置驱动变换 + 插件（typed_ports 展开等） | `transform/`（engine 插件） | 消费 analyze 建的语义映射表（`type_ports_flat` 等，组件 postpass 展开供源） | `core/component_protocol.md` |
| renderer | Doc IR 布局 → 文本（注释回插） | `renderer/`（doc/renderer/node_renderer/primitives） | 世界 A：引擎源端渲染 | `renderer/renderer_architecture.md` |
| format?（可选） | formatter 插件 pass 管线 | `grammar/verilog/plugins/formatter/` | 世界 B：覆盖式/精排（语言包声明启用） | `grammar/verilog/plugins/formatter/README.md` |

**阻断语义**（哪站失败会停，防静默错乱）：lint 有诊断停（`no_lint` 是显式逃生
门）；parse 未消费 token 停；analyze pass error 级语义诊断停调度停管线。
细节见 `docs/pipeline_stages.md`。

## 两条知识面：语言数据 vs 引擎骨架

| | 内容 | 位置 |
|---|---|---|
| 语言数据 | 语法规则 / token 定义 / 检查规则 / 插件声明——**全部 TOML** | `grammar/{verilog,c4,yaml}/` + 语言包 `tpc.toml` |
| 引擎骨架 | 词法/语法/语义/变换/渲染的**通用算法 + 编排**——语言无关 | `lexer/` `parser/` `linter/` `analyzer/` `transform/` `renderer/` `preprocessor/` `core/` `pipeline/` |

分界纪律（硬约束）：**语言知识不进代码**——引擎不得硬编码任何语言具体知识
（规则名/token 类型/结构名/表达式形态一律由 grammar TOML 提供）。改语言行为
改 `grammar/` TOML，改引擎能力才改骨架代码。

插件是"半语言数据半引擎"的桥：`grammar/*/plugins/*/` 用 tpc.toml 声明语法注入
（`[grammar]`）、语义原语（`[analyzer]`）、变换槽位（`[transform]`）、检查 pass
（`[[pipeline.pass]]`）、能力入口（`[capabilities]`）、渲染插件（`[render]`）——
见 `core/component_protocol.md`。

## 横切机制（不是某一站，贯穿全程）

- **配置注册制**（`core/config_registry.py`）：declare_cfg 三阶段时序（import
  注册 → load_all 推送 → 运行读取）；语言包自包含 `resolve`。怪象与规避见
  `core/config_lifecycle.md`。
- **组件协议**（`core/plugin_loader.py`）：插件 tpc.toml 声明 → 发现/依赖排序/
  加载；魔数键集中在 `core/_protocol.py`。见 `core/component_protocol.md`。
- **核心类型**：Token/GrammarRule/Node/FileManager（`core/define.py`），错误层级
  （`core/errors.py`）。
- **核心类型即接口**：token 类型命名协议（`core/token_protocol.py`）是 lexer 与
  parser/linter 之间不写裸字符串的单一事实源。

## 下钻路线（怎么用这份文档）

1. 想理解引擎全貌 → 就停在这份文档（一遍即可）。
2. 想改某个子系统 → `MODEL_INDEX.md` 跳转表（知识单元 → 文档位置 → 实现 →
   验证）→ 对应机制文档（上表"深入读"列）→ `Impl:` 位置。
3. 想从零搭一门语言 → `language_walkthrough.md`（教程，c4 实例）——那条线是
   "照着 c4 填 TOML"，不是改引擎。
4. 想知道当前在推进什么 / 哪些没做 → `TODO.md`（短期）+ `ROADMAP.md`（中长期）。

> 本文件维护纪律：只讲骨架与衔接，不把某站细节复制进来（重复即删，见
> `policy/doc-alignment.md`）；阶段线变了就同步这里 + `docs/pipeline_stages.md` +
> `MODEL_INDEX.md` 三处。
