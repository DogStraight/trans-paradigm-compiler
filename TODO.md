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

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- B 类消歧 = 动态两级：Level 1 变长前瞻（前缀路径，seen 以路径开头匹配）+ Level 2 试解析
  （候选生成式复杂时完整 production 匹配，复用 RuleMatcher）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待 Phase 5 增强）
