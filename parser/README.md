# parser — 语法解析（递归下降 + Pratt + 规则选择）

> tokens → AST。语言规则（production）全来自 `grammar/` TOML，本包是通用
> 递归下降引擎 + Pratt 表达式 + 规则选择 + FOLLOW 派生，不含任何语言知识。
> 想改某文件先看下方一句话；机制深挖见 `Doc:` 反引与 `docs/MODEL_INDEX.md`。

| 文件 | 一句话 |
|------|--------|
| `parser_core.py` | Parser 主引擎：递归下降 + 回溯（`Parser.parse` 入口，块/普通链调度） |
| `_production.py` | 生产式匹配主循环（parse_token/call/seq/choice + 注释收集挂载） |
| `_comment_trivia.py` | 注释位置判定单点实现（前一显著 token / 独占行 / 行中）——生产侧与表达式侧共用 |
| `block_parser.py` | 块 & 语句级解析（行首规则领挂独立行注释 / Comment 子节点） |
| `pratt_parser.py` | Pratt 表达式解析（运算符优先级 + 行中/行尾/独占行三分类注释挂载） |
| `rule_selector.py` | 候选规则过滤（start token 匹配）+ production 树序列化 |
| `follow.py` | FOLLOW 集派生（后继合法性，对标 yacc，end_case 已并入） |
| `attribute_binder.py` | `$N` node 绑定 & 路径提取 |
| `grammar_inject.py` | 语法规则注入（production 注入/传播/替换，树层结构化） |
| `_constants.py` | 包内共享常量（token 类型 re-export） |

> 入口：`Parser.parse`；改注释机制相关挂载（行中/trailing/leading/独占行）先进
> `_production.py::collect_following_comments` / `pratt_parser.py`。
> **规则内部注释**另有一道**让位闸门**：`prepare_production` 调
> `_comment_trivia.comment_leave_to_expression`（判据 = 元素是 pratt 规则调用 +
> 注释**非行中** + `context.production_pointer > 0` + 注释前 token 下标 ≥
> `context.production_start_ptr`）——不吞注释、留给表达式入口按独占行/行尾归位
> （`leading_own_line` / `leading`）；两字段由 `match_productions` 维护并入回溯快照。
> 位置判定与**通道分工优先级**统一在 `_comment_trivia.py`（模块 docstring 有表：
> 行中 → 节点槽 / 规则内部 → 让位闸门 / 列表项间 → 容器上浮 / 首元素前 →
> `_claim_head_comments` / 其余独占行 → line 通道锚条目）。收敛前同一判定三处实现、
> 语义不一致。
> 表达式系统约定（`[[operator]]` 数组顺序=优先级 / is_atom / 一元-二元/三目 /
> 结合性）见 `parser/expression_conventions.md`。
