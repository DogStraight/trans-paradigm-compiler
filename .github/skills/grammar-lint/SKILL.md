---
name: grammar-lint
description: '静态检查 TOML 语法规则配置文件，提前捕获常见的配置错误、循环引用、节点映射越界。用于规则修改后验证或 new-lang 脚手架集成。'
user-invocable: true
argument-hint: '可指定 --rules-dir 参数，默认 grammar/rules_verilog'
---

# Grammar Lint — 语法规则静态检查

## 适用场景

- 修改 TOML 规则文件后验证
- 代码审查前检查规则一致性
- 新增语法规则后确认无遗漏
- 调试解析异常时排查规则配置错误

## 使用方法

```bash
# 默认检查 grammar/rules_verilog/
python .github/skills/grammar-lint/scripts/lint_grammar.py

# JSON 格式输出
python .github/skills/grammar-lint/scripts/lint_grammar.py --format json

# 指定自定义规则目录
python .github/skills/grammar-lint/scripts/lint_grammar.py --rules-dir ./my-grammar
```

## 检查清单

### 1. 缺少生产式（Error）

规则没有 `production`、`block_start`、`pratt`、`atomic` 中的任何一个：
- 必须至少定义一个，否则解析器无法匹配

### 2. 引用不存在的规则（Error）

`@RuleName` 指向一个未定义的规则：
- 检查拼写错误
- 检查是否忘记在 TOML 文件中定义

### 3. 节点映射越界（Error）

`$N` 引用的产生式序号超出规则的实际生产式数量：
- `$1` 引用第一个产生式，`$2` 引用第二个，以此类推
- 如果规则有 3 个生产式，`$4` 就是越界

### 4. 循环引用（Warning）

规则 A → B → C → A 的引用链：
- 语法规则中的循环通常通过 `end_case` 终止条件处理
- 如果某个循环没有对应的 `end_case`，会导致栈溢出

### 5. Inline 规则多属性（Warning）

Inline 规则有多个 `node` 属性映射时，只有第一个被 inline 扁平化使用

### 6. Block 规则无 block_end（Warning）

设定了 `block_start` 但没有对应的 `block_end`

### 7. 未使用的规则（Info）

定义了但从未被任何 `@RuleName` 引用的规则：
- 可能已废弃，可清理
- 也可能是通过 `parse_block_body` 间接使用的入口规则

### 8. Atomic 规则无 end_case（Info）

`atomic = true` 的规则没有 `end_case` 可能会贪婪匹配

## 输出解读

```
============================================================
  Grammar Lint Report — rules_verilog
  Rules: 108  Issues: 29 (E:0 W:15 I:9)
============================================================

  Warnings:
    W  04_statements.toml [BasicStmt]  Circular reference detected

  Infos:
    I  05_expressions.toml [Identifier]  Atomic rule has no end_case
```

- **E**（Error）— 必须修复，会导致解析失败
- **W**（Warning）— 可能导致意外行为，建议审查
- **I**（Info）— 信息提示，根据情况决定是否处理

## 项目规则

- 所有规则文件放在 `grammar/rules_verilog/` 目录
- 以下划线 `_` 开头的文件被跳过（`_token.toml`、`_pratt.toml` 等）
- `Inline` 规则应只有一个属性映射
- `Atomic` 规则通常用于表达式层级，不需要 `end_case`
