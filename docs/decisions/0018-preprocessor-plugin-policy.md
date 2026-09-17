# ADR-0018: 预处理器边界——引擎只做文本操作，展开策略走语言插件能力

- Status: accepted
- Date: 2026-09-17
- 关联：`docs/decisions/0017-macro-in-syntax-position.md`（宏位处理现行机制）、
  `preprocessor/README.md`（契约落地）、`ROADMAP.md` P3.6（分期剩余项）

## 背景

预处理器（`preprocessor/`）里混着两类东西：

1. **文本操作 / 通用机制**（语言无关）：宏体替换、条件编译路径、文件包含、
   指令处理器分发、锚 + 原文还原、宏区间与行映射。
2. **语言知识**（写在了引擎里）：

   | 位置 | 内容 |
   |---|---|
   | `_expand.expand_tokens` 4 个分支 | 展开策略判定：整行占位 / 空体 inline 锚 / 独占一行补分号 / 语义替换 |
   | `_match_paren_args`、`_split_args` | 函数宏实参形态（定界符 `()`、嵌套 `[]`、分隔符 `,`） |
   | `_LITERAL_SUFFIX_RE` | 宏调用后随位宽字面量后缀（`'s` / 进制 / digit 集） |
   | `expand_tokens` 的 `if "//" in tail` | 注释标点（同族"注释标点声明驱动"清理的漏网项） |

   后果：换一门语言要改引擎；与 grammar / analyzer / transform 已确立的
   "语言知识在语言包（TOML 声明 + 插件）" 不一致。

## 决策

1. **引擎只保留文本操作与通用机制**：splice（宏体铺进流）、条件编译、include、
   锚/区间记账、还原、行映射、指令处理器分发。判定"此处该怎么处置"的知识不进引擎。
2. **引擎定义处置枚举**（机制面，可审计、可对拍；与铺条目 `mode` 同词）：
   `splice` / `line` / `inline` / `token`（可带 `append`）。
3. **语言包用既有 `[capabilities]` 能力机制声明策略入口**
   （`macro_policy = "file.py:fn"`，与 formatter 同款，见 `core/component_protocol.md`）。
   引擎给**通用文本事实**（调用点上下文：名字 / 宏体 / 行列 / 行内前后文 /
   是否独占一行 / 是否语义模式），策略返回处置枚举。
4. **能力按 rules_dir 作用域查找**（语言包目录下的组件才有资格应答）——
   不依赖"当前装载语言"的全局状态，跨语言不串用（新增
   `core/plugin_loader.get_capability_in`）。
5. **未声明能力 → 引擎默认 `splice`**：纯文本替换 + 宏区间（渲染侧靠区间 raw
   拼接）；要保真还原宏调用原文（空体宏/整行宏等形态）的语言包自行声明策略。
6. **声明面已有形态不进插件**：注释标点、续行符、指令关键字、宏形态一律从
   语言包声明取（本决策顺带修掉 `//` 硬编码漏网项）。

## 权衡

- 代价：多一层"引擎问策略"的间接（每宏调用一次调用）；verilog 的现有保真行为
  依赖其策略插件在场；策略返回非法枚举 → fail-fast（新增失败面）。
- 拒绝的备选：
  - **纯 TOML 策略表**（引擎解释条件）——判定条件本身是语言知识，表会演化成
    小型 DSL；与 analyzer 已有的"L1 声明式 + L2 插件 handler/postpass"分工重复。
  - **维持现状**——语言知识继续写在引擎里，换语言改引擎。

## 验证

- worktree A/B 对拍：107 个样本输出逐文件一致（成功标志 / 长度 / sha256 全同）；
- 全量测试 + 真实语料三工具持平（lint 33/33 / 误报 0、diag 5548、宏覆盖 86/135）；
- 新增 `tests/engine/preprocessor/test_macro_policy.py`：未声明能力 → 默认 splice、
  各 mode 的执行效果、非法方案 fail-fast、语言作用域（c4 不拿 verilog 的策略）。

> Impl: `preprocessor/macro_policy.py`、`grammar/verilog/plugins/macro_policy/_policy.py`
> Test: `tests/engine/preprocessor/test_macro_policy.py`
