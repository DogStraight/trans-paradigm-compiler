# TODO — 后置边界问题

> 发现器多层级化 + 两级消歧完成后暴露的边界问题（用户明确：接受误报，边界管理，
> 此清单后置处理，不阻塞当前全绿状态）。

## linter 边界问题

- [ ] **表达式内运算符后换行（多行 RHS）误报**：`a <= b +\n c;` 中 `+` 后换行被 pratt 视为表达式终止
  - 根因：`parser/pratt_parser.py` 无 newline/trivia 跳过逻辑（表达式不跨行）
  - 影响：`a = b +\n c;`、`a <= (b +\n c);` 等运算符后换行被误报 "expected ';' got 'id'"
  - 方案：pratt 解析时跳过 newline（或 linter 表达式检查预折叠换行），需评估对 parser 主流程影响
- [ ] **`always @*` 敏感列表误判**：`always @* begin` 中 `@*` 被当 `@(` 期待括号（`test_nested_begin_end` 相关）
  - 根因：`@` 后 `*`（symbol.base.multiple）与 `@(...)` 的消歧边界
- [ ] **while/repeat 语句无完整语法规则**：`while`/`repeat` 已定义为关键字（token.toml），
  - 但 grammar 无对应语句规则（RepeatStmt/WhileStmt），发现器跳过其内部（body 语句仍被发现）
  - 方案：如需检查 while/repeat 结构，补充对应语法规则（语法扩展，非 linter 改动）
- [ ] **function 有范围头漏检**：`function [7:0] add(...)` 的 `@Range?` 非原子 call 截断判别
  - 路径，`[`（范围）不匹配 paths → function 块不发现（漏检整个 function）
  - 根因：`_feat_token_paths` 对非原子 call（@Range 等在判别点前）返回 None 截断，丢 first 集
  - 方案：可选头元素（@Range?）保留 epsilon 分支 + 复杂分支截断（或非原子 call 返回 first 集）
- [ ] **带下标赋值目标漏检**：`data[i] = i;`（for/always 内）的 `data[` 首判别 token 是 `[`
  - （select），B 类 paths 只认 `=`/`<=`/`(` → 语句不发现
  - 根因：B 类判别点要求 @PrimaryExpr 后第一个 token 是 =/<=/(，不覆盖 select 目标
  - 方案：B 类对 `id [` 前缀也判为赋值/调用候选（或 Level 2 试解析覆盖）

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
