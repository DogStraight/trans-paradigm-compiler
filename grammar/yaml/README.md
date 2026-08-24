# yaml — YAML 子集迷你语言包

验证 tpc 的**缩进 token 机制**（`space.indent`/`space.dedent`）的迷你语言包。

## 为什么是 YAML

YAML 的块结构**完全靠缩进定界**（无大括号/end 关键字），是缩进语法的
最纯粹验证样本。c4/verilog 都是 `[indent] enable = false`（大括号/关键字
定界），缩进机制从未被任何语言包启用过——本语言包是第一个。

## 子集范围

- 映射：`key: value`（value 为标量或缩进块）
- 列表：`- item`（item 为标量或缩进块）
- 标量：字符串/数字/布尔（true/false）/null
- 注释：`#` 行注释
- 缩进：4 空格 = 1 级（`[indent] level = 4`）

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
- 不支持：流式集合（`[a, b]`/`{a: b}`）、多行字符串、锚点/别名、类型标签。