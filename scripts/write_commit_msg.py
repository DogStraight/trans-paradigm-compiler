"""临时脚本：写入提交信息"""
msg = """refactor(parser): 解析器大规模硬编码消除与原子规则重构

- GrammarRule.__init__: 数据驱动替代 elif 硬编码链
- 新增 atomic 标记: 标记原子规则(括号/函数调用/拼接/索引等)
- 新增 _parse_atom 动态匹配: 遍历 atomic_rules 尝试完整规则匹配
- 移除 _collect_expr_tokens / _preprocess_calls / _parse_call_args / _parse_single_arg
- 改造 Pratt 解析器: 新增 atom_parser 回调 + stop_tokens 参数
- 消除产生式字符串模式匹配(startswith("@")/endswith("?")等)
- 统一内部 AST 节点名与特征类型名: sequence->seq, list->repeat
- Token 分类配置化: is_* 函数由 _token.toml 中 [token_category] 驱动
- 修复: 规范化配置加入 literal.number 等字面量提取, 解决数字丢失
"""
with open("COMMIT_MSG.txt", "w", encoding="utf-8") as f:
    f.write(msg)
print("COMMIT_MSG.txt written")
