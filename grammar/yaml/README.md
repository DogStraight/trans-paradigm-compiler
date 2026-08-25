# yaml — YAML 子集语言包

验证 tpc 的**缩进 token 机制**（`space.indent`/`space.dedent`）的语言包，
并逐步补全为有实际解析价值的 YAML 子集（流式集合/锚点/多文档，零引擎改动）。

## 为什么是 YAML

YAML 的块结构**完全靠缩进定界**（无大括号/end 关键字），是缩进语法的
最纯粹验证样本。c4/verilog 都是 `[indent] enable = false`（大括号/关键字
定界），缩进机制从未被任何语言包启用过——本语言包是第一个。

## 子集范围

- 映射：`key: value`（value 为标量或缩进块）；key 可为 merge key（`<<: *defaults`）
- 列表：`- item`（item 为标量或缩进块）；**行内映射**（compact mapping）：
  `- name: Test` + 同列对齐续块（`  run: |` 兄弟成员，见 00_document.toml
  的 CompactMap/SeqValue 规则）
- 流式集合：`[a, b]` / `{k: v}`（可嵌套、可跨行，见 01_flow.toml）
- 块标量：`key: |`（字面）/ `key: >`（折叠），含切块/缩进指示符原样保留
  （见 base/_token.toml 的 [[capture]] indent_leq mode）
- 标量：字符串/数字/布尔（true/false）/null
- 锚点/别名：`&anchor value`（声明）/ `*alias`（引用，仅解析不做展开语义）
- 多文档：`---`（文档分隔）/ `...`（文档流结束），顶层语句形态
- 注释：`#` 行注释
- 缩进：`[indent] level = "auto"`——单位从文件推导（首次结构缩进行锁定，
  Python 同款），2/4/6 空格文件均可解析；渲染跟随源文件锁定单位（AST
  根节点 _indent_unit → renderer）

## 机制验证点

1. **lexer 缩进 token**：`[indent] enable = true` 时，lexer 按缩进网格生成
   `space.indent`/`space.dedent` token（每级一个）
2. **缩进块作为块边界**：`IndentBlock` 规则 `is_block = true`，
   `production = ["space.indent", "space.dedent"]`——`block_start`/`block_end`
   从 production 首尾字面 token 推导为 `space.indent`/`space.dedent`
3. **块 body 循环**：`IndentBlock` 的 body 由 `parse_block_body` 循环
   `parse_sentence` 解析子项（MappingEntry/SequenceItem）
4. **嵌套归属**：`key:` 后无标量时，`@Value?` 匹配 `@IndentBlock`（下一行的
   `space.indent`），块正确挂在 `MappingEntry` 的 value 下（嵌套 AST）

## 引擎修复（本语言包暴露）

- **`indent_deep` 跨调用残留**：`Lexer.tokenize` 不重置 `indent_deep`，多次
  tokenize 间累积——新文件开头误发 `space.dedent`。已修：`tokenize` 开头
  重置 `indent_deep = 0`（每个源文件独立缩进上下文）。c4/verilog 的
  `indent_enable = false` 从未暴露此问题。

## 已知边界

- **renderer body 固定缩进**：`render_node` 的 body 渲染固定 `Break + Nest`
  缩进 1 级（`body indent = false` 不生效，c4 的 AsmProgram 同样带 4 空格
  缩进）。YAML 渲染输出每层多 4 空格（顶层 4、嵌套 8）——这是引擎行为，
  非语言包问题；本语言包聚焦验证缩进 token 机制，不追求渲染保真。
- **引号转义不支持**：`'it''s'` / `"a\"b"` 无法解析——引擎字符串分支是手写
  字符循环（lexer/main_lexer.py），不认转义；加转义需动引擎（影响 verilog
  字符串行为），收益小，不做。简单引号字符串（无转义）可用。
- **流式集合跨行渲染回单行**：输入 `[1,\n 2]` 输出 `[1, 2]`——渲染不保留
  括号内换行（join 原语扁平化）。
- **锚点/别名仅解析不展开**：`*alias` 是语法节点（AliasRef），无语义层
  别名展开/锚点作用域检查——本语言包聚焦语法与渲染。
- **块标量逐字捕获，不做语义展开**：内容原样入 `literal.block_scalar` token
  （含指示符行与切块/缩进指示符 `|-`/`|+`/`|2`）；折叠（`>`）、chomping
  语义不做处理；指示符行上的注释（`| # c`）随内容一体捕获（非独立
  comment token）。终止条件 = 非空行缩进 ≤ 触发行缩进（列比较，与
  4 空格缩进网格无关）。
- **多文档是扁平语句**：`---`/`...` 解析为顶层 DocStart/DocEnd 节点
  （渲染保真），无 per-document 语义隔离。
- **plain scalar 字符集窄**：bare 值只认字母数字下划线——真实配置值里
  常见的 `${{ }}`（CI 表达式）、`/`（路径/URL）、`@`（`actions/checkout@v4`）、
  中缀 `-`（`windows-latest`）都不在字符集内；多词值（`echo hi`）也
  不支持（值 = 单 token）。这是"解析真实配置文件"的下一个阻塞点
  （实测 ci.yml 死于 `${{ matrix.os }}`）。
- 不支持：类型标签（`!!str`）、`%YAML` 指令、多行字符串、plain scalar
  完整规则（终止条件/复杂键隐式规则等）。