# Linter 重构计划 — 发现 + 扁平检查架构

> 状态: 进行中 (2026-07-31)
> 目标: 将现有"单遍在线、依赖首 token 选规则"的 P2，重构为"发现 + 扁平检查"两阶段架构。

## 背景

当前 `linter/scanner.py`（307 行）的 P2 依赖 `_start_map` + `_consume` 做轻量语句识别，存在两个问题：

1. **首 token 敏感**：一个 token 命中多规则（`foo` 可能是赋值/实例化/调用/声明器），靠首 token 猜语句结构很脆弱
2. **错误信息笼统**：只能报 `syntax error: unexpected 'x'`，说不出"这里期望什么"

## 核心架构（两阶段）

```
token 流 + 骨架树（块配对）
  ↓ ① 发现阶段（discovery）
  token 流变形成"自动注册的轻量 AST"：
    块区域划分（上下文：module_body / proc_body / gen_body）
    逐语句起点：关键字触发 或 动态前瞻消歧（标识符触发）
    语句 body 下钻（always→if→assign）→ 递归发现嵌套节点
  ↓ ② 检查阶段（扁平 validate）
  每个注册节点实例化对应 Checker，独立 validate()
  错误合并 → LSP 兼容 LintDiagnostic
```

**轻量 AST 节点**（发现阶段产物 = 自动注册的检查器列表）：

```python
{
  "type": "statement",   # 或 "bound" / "token"
  "rule": "AssignStmt",
  "start": 5, "end": 11, # token 区间
  "children": [...],     # 嵌套发现的子结构
  "context": "module_body"  # 消歧用的块上下文
}
```

## 目标目录结构

```
linter/
├── scanner.py          # 两阶段编排入口（保留 LinterScanner 接口兼容）
├── discovery.py        # token 流 + 骨架 → 轻量 AST（自动注册形态）
├── checker.py          # Checker 协议 + 注册表
├── lookahead.py        # 动态前瞻消歧表（FIRST_k 集）
├── checkers/
│   ├── __init__.py
│   ├── boundary.py     # 边界检查器（迁移原 P1）
│   ├── macro_token.py  # 宏 token 检查器（迁移原 P0）
│   ├── statement.py    # 语句检查器（从 production 编译）
│   └── expression.py   # 表达式检查器（借力 pratt parse_with_count）
├── grammar_slicer.py   # 已有（复用）
└── cli.py              # 已有（不变）
```

## 已对齐的决策

1. **发现消歧**：动态前瞻（lookahead），逐级缩小候选规则集
2. **中间形态**：两阶段，token 流 → 轻量 AST（比完整 AST 更轻，只服务语法检查）
3. **表达式**：借力 parser 的 pratt 部分（`parse_with_count`），独立检查器

## 语法文件研究结论（发现机制的设计依据）

- 规则分两层：**选择器层**（inline 无 token：`CtrlStmt`/`Stmt`/`DeclStmt`/`InstStmt`... 在 `04_statements/00_base.toml`）与**叶子层**（有 production）
- 触发方式两类：
  - **A 类关键字触发**（易发现）：`assign`/`if`/`for`/`always`/`case`/`wire`/`reg`/`begin`/`module`/`generate`/`function`/`;`
  - **B 类 @Identifier/@PrimaryExpr 触发**（需消歧）：`BlockingAssign`/`NonBlockingAssign`/`ModuleInst`/`SubroutineCall`
- **上下文可砍掉一半歧义**：模块体 vs 过程体（骨架树提供）
  - 模块体不可能有 `BlockingAssign`/`SubroutineCall`
  - 过程体不可能有 `ModuleInst`/`WireDecl`
- end_case 基本完备（语句类 `["newline"]`，`Expression` 是分隔符集，`Declarator` 用排除式 `["!symbol.base.dot"]`）
- bound 块：`ModuleDecl`(module/endmodule)、`BeginEnd`(begin/end)、`GenerateBlock`(generate/endgenerate)、`Root`

## 复用资产

| 资产 | 位置 | 用途 |
|------|------|------|
| `parse_with_count` | `parser/pratt_parser.py` | 表达式检查器底层 |
| `select_candidates` 消歧思路 | `parser/rule_selector.py` | 候选过滤 + 排序参考 |
| `ParseContext` 快照/回溯 | `parser/parser_core.py` | 错误恢复参考 |
| `build_slice_tree` / `get_start_tokens` | `linter/grammar_slicer.py` | 规则结构 + FIRST 集基础 |
| `_all_bracket_openers/closers` | `scanner.py`（迁移） | bracket_map 配置推导的括号集 |
| `_block_openers/closers/pairs` | `scanner.py`（迁移） | 边界配对基础 |

## 实施步骤

### Phase 0 — 基础设施
- `checker.py`：`Checker` 协议（`validate(tokens) → list[LintDiagnostic]`）+ 注册表
- 迁移 bracket/block 集合初始化到可复用模块

### Phase 1 — 边界检查器（迁移 P1，最成熟作模板）
- `checkers/boundary.py`：封装 `_phase1_boundary` 配对逻辑
- 发现器：扫描 block openers/closers → 产出 bound 节点
- 验证：`test_linter_boundary.py` 全过

### Phase 2 — token 检查器（迁移 P0）
- `checkers/macro_token.py`：封装 `_phase0_token_check`
- 验证：原 P0 相关测试全过

### Phase 3 — 语句发现器 + 动态前瞻消歧（核心难点）
- `lookahead.py`：从 production 树预计算前瞻表（FIRST_k），规则按关键字/标识符分类
- `discovery.py`：骨架划分区域（上下文）→ 逐语句起点发现 → body 下钻
- 验证：normal 28 文件发现的语句类型与人工核对

### Phase 4 — 语句检查器（从 production 编译）
- `checkers/statement.py`：从 production 树编译匹配函数（闭包），token 位置知道期望
- call 展开策略：遇 `@Expression`/`@PrimaryExpr` 交 ExpressionChecker（防爆炸）
- 验证：normal 28/28 零误报 + 坏样本报精准错误

### Phase 5 — 表达式检查器（借力 pratt）
- `checkers/expression.py`：封装 `parse_with_count`，加载 `parser.operator_defs`
- 验证：表达式坏样本能精准报出

### Phase 6 — 编排整合 + 移除旧逻辑
- `scanner.py`：`scan()` = 发现 → 注册 → 扁平 validate → 合并错误
- 移除旧 `_phase0/_phase1/_phase2`、`_start_map`、`_consume`、`_skip_to_end`
- 验证：全量 pytest 228 过 + normal 28 零误报 + CLI 抽查

## 验证总纲

1. 每 phase 后：`python -m pytest tests/ -x -q`（228 个逐步不破）
2. normal 组零误报：`verilog/tests/normal/ref/*.v` 全零错误
3. 精准性：每语句类型构造坏样本，断言错误含具体期望 token
4. CLI 抽查：`python linter/cli.py <file>` 输出与现有一致

## 明确排除（scope）

- 不做完整 AST（不解析表达式细节、不绑定 $N 属性、不建符号表）
- 不改 parser/ 主解析器（只借力 pratt 和规则结构）
- 不做自动修复（fix），只报错
- 不引入插件扩展点（先保证现有语法覆盖）

## 风险

- **B 类消歧**是最大不确定点：`foo = x` vs `foo bar(...)` vs `foo(...)` 的前瞻判定需实测校准
- **call 展开深度**：`@Expression`/`@PrimaryExpr` 无限内联会爆炸 → 语句检查器不深入表达式
- **发现阶段误判语句边界**会连锁 → 用 end_case + 块骨架兜底
