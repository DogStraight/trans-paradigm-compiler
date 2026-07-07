# PyV Compiler 编码风格

## 总则

- 项目语言：**中文注释为主**，英文保留给术语/代码引用
- Python 3.11+，零外部依赖
- 遵循 PEP 8，但以下规则优先

---

## 1. Docstring

### 1.1 模块级 docstring

每个 `.py` 文件顶部必须有一个模块级 docstring，用 `"""`：

```python
"""模块名称 — 一句话职责。

可选：第二段详细说明。
"""
```

- **一行能说完就用单行**，不要写空的 `""""""
- 如果有多行，第一行是摘要，空一行后跟正文
- 正文每行不超过 80 字符

示例：

```python
"""RuleSelector — 基于起始 token 的候选规则过滤。"""
```

```python
"""ParseContext — parser state container with snapshot/restore for backtracking."""
```

### 1.2 类 docstring

```python
class Foo:
    """一句话说明类的职责。

    Attributes:
        attr1: 说明
        attr2: 说明
    """
```

简单类可以直接用单行：

```python
class ScopeEntry:
    """作用域条目"""
```

### 1.3 函数/方法 docstring

用单行 `"""..."""`，除非需要参数说明：

```python
def has_more_tokens(self) -> bool:
    """判断是否还有未解析的 token。"""
```

```python
def parse_block_body(self, context: ParseContext, block_node: Node, matched_rule: GrammarRule) -> Optional[Node]:
    """解析块体内容。

    Args:
        context: 当前解析上下文
        block_node: 块 AST 节点
        matched_rule: 匹配的块规则

    Returns:
        解析后的块节点，失败时返回 None
    """
```

- Args / Returns / Raises 节用 `Args:` / `Returns:` / `Raises:` 显式标记
- 参数与类型之间不需要重复类型（类型由注解提供）

---

## 2. 内联注释

### 2.1 行注释

```python
# 这是一个中文注释
x = 1  # 短注释放在代码后，两个空格分隔
```

- `#` 后**必须跟一个空格**，然后才是文字
- 中文注释**以句号结尾**（当它是完整句子时）
- 短注释（跟在代码后）可以省略句号
- 英文术语保留原样，不用翻译

```python
# 从嵌套的阶段结构中提取属性到顶层，同时保留原始嵌套。
for stage in ("parser", "analyzer", "renderer"):
    ...
```

```python
x = fn()  # 跳过空白
```

### 2.2 块注释

多行注释统一用连续的 `#` 行（不要用 `"""` 做多行注释）：

```python
# 第一行。
# 第二行。每行都是完整句子，以句号结尾。
```

### 2.3 TODO / FIXME / HACK

```python
# TODO(username): 什么需要做，为什么
# FIXME: 这里有已知问题，原因是什么
# HACK: 临时绕过了什么，计划如何修复
```

---

## 3. 章节分隔符

### 3.1 模块级章节

使用 `# ═══ ... ═══` 或 `# ─── ... ───`，与类/函数的边界对齐：

```python
# ═══════════════════════════════════════════════════════════════
# ScopeStack — 轻量作用域栈
# ═══════════════════════════════════════════════════════════════
```

或者简短的 `# ──`：

```python
# ── 快照/恢复（配合 parser 回溯） ──
```

### 3.2 文件内功能分区

在函数/流程的段落之间，用 `# ----`：

```python
# ---- Stage: Lexical analysis ----
```

```python
# ---------------------------- Helpers ----------------------------
```

**规则**：
- 顶层分区用 `# ═══` / `# ───`（全宽分隔）
- 函数内部的段落用 `# ----`（短横线）
- 分隔线长度 = 所在缩进 + 至少 40 字符

---

## 4. 类型注解

统一使用 PEP 484 注解语法，Python 3.11+ 原生泛型：

```python
# ✅ 正确
def load(name: str) -> dict[str, int]: ...

# ❌ 错误（老式）
def load(name: str) -> Dict[str, int]: ...
```

- `Optional[X]` 等价于 `X | None`，优先使用 `X | None`
- `list[X]`、`dict[str, Y]`、`set[Z]` 而非 `List[X]` 等
- 来自 `collections.abc` 的类型（`Mapping`、`Sequence`）保留完整导入
- 类型别名用大写驼峰

```python
RuleTable = dict[str, GrammarRule]
```

---

## 5. 命名约定

| 类别 | 约定 | 示例 |
|------|------|------|
| 函数/方法/变量 | `snake_case` | `parse_block_body`, `statement_rule_names` |
| 类/规则名/节点类型 | `PascalCase` | `RuleSelector`, `ModuleDecl`, `GrammarRule` |
| 私有成员 | `_prefix` | `_resolve_peek`, `_CACHE` |
| 常量/枚举 | `UPPER_CASE` | `LOG_WARN`, `_ORDER_NOT_FOUND` |
| 模块内部未使用参数 | `_name` 或 `_` | `def fn(_unused, used):` |
| 模块级缓存/单例 | `_UPPER_CASE` | `_PIPELINE_SHARED`, `_DEFAULT_CACHE_PATH` |

---

## 6. 代码布局

### 6.1 Import 顺序

```
# 1. 标准库
import sys
import os

# 2. 第三方（本项目零外部依赖，此区为空）

# 3. 项目内部
from core.define import Node, Token
from .parser_core import Parser
```

各组之间空一行。同组内按字母序。

### 6.2 类布局

```python
class MyClass:
    """Docstring."""

    # 类常量/类变量
    CONSTANT = 42

    def __init__(self):
        ...

    # ── 公共 API ──
    def public_method(self):
        ...

    # ── 私有方法 ──
    def _helper(self):
        ...
```

### 6.3 空行

- 类定义之间：2 个空行
- 方法定义之间：1 个空行
- 函数内逻辑段落：1 个空行

---

## 7. 字符串与引号

- 字符串用 `"`（双引号），除非内容含双引号
- docstring 用 `"""`（三个双引号）
- 字符串格式化用 f-string

```python
name = "world"
greeting = f"Hello, {name}!"
```

---

## 8. 异常与错误处理

### 8.1 ParseError

Parser 专用异常，携带失败上下文。构造时使用关键字参数：

```python
raise ParseError(
    msg="描述",
    token=current_token,
    rule=rule.name,
    path=context.path,
)
```

### 8.2 解析异常

解析失败时抛出 `ParseError`（携带 token/rule/path/candidates 上下文）。

---

## 9. 日志

管线内用 `_log()` 代替 `print()`，`quiet` 模式隐藏：

```python
_log(f"[lexer] tokens: {len(tokens)}")
```

Parser 内部用 `self._log_state(action, level, context)`，等级常量：

```python
self.LOG_DEBUG  # verbose 模式可见
self.LOG_INFO   # 始终输出到日志文件
self.LOG_WARN   # 日志文件 + stderr
self.LOG_ERROR  # 日志文件 + stderr
```
