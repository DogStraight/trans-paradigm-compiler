# Coding Style

## 注释语言

- 注释、docstring、行内说明 **以中文为主**（项目现状即中文主流，规范贴合现实，
  不强制英文——强制英文会导致生成时风格漂移）。
- 例外：**配置需求标记**（`# lexer.token_base` 等，指向 TOML 配置键）保持英文——
  因为配置键本身是英文，标记与之一致便于 grep。
- 面向外部读者的文档（README / CONTRIBUTING / API 参考）仍以英文为主（若对外发布）。

## 注释风格

- **分区标题**：统一 `# ── 标题 ──`（全角横线，两侧各一个空格）。
  - ✅ `# ── 配置需求 ──`
  - ❌ `# ============ 配置需求 ============`
  - ❌ `# ---- Stage: xxx ----`
  - 分隔线长度不强制（`# ── xxx ──` 或 `# ── xxx ──────────────` 均可，
    以"标题可见"为准），但**符号统一为 ──**。
- **说明句**：`# 动词/名词短语`，中文，简洁。
  - ✅ `# 从规则推导块边界`
  - ❌ `# This is a function that does something`（除非是配置键标记）
- **行内注释**：`#` 后一个空格。`code  # 说明`（代码与 `#` 间至少一个空格）。
- **docstring**：`"""模块名 — 职责描述。"""` 单行；多行用
  `"""第一行摘要\n\n详细描述\n"""`。文件头 docstring 末行保留
  `Doc: docs/xxx.md`（对齐约定，见 docs/README.md）。
- **TOML 注释**：同样中文为主，`# 说明`，配置键/规则名用英文原样。
  - ✅ `# 对齐参考实现 rswier/c4 的 next()`
  - ❌ `# This aligns with the reference implementation`
- **TOML 分区标题**：规则/段之间的分区说明用 `# ── 标题 ──`（同 Python）。
  - ✅ `# ── 过程体赋值 ──`
  - ❌ `# ---------- 过程体赋值 ----------`
- **TOML 文件头 banner**：整块说明（模块用途/对齐来源/约定）用 `# ====` 包裹
  上下框线（这是 TOML 无 docstring 的对应物，允许保留）：
  ```toml
  # ============================================================================
  # 30_assign.toml — 赋值语句规则
  # ============================================================================
  ```

## 命名

- Python: `snake_case` for functions, variables, methods.
- Node types / rule names: `PascalCase` (e.g. `Declarator`, `ModuleInst`).
- Private: `_prefix` (e.g. `_match_productions`, `_CACHE`).
- Constants: `UPPER_CASE` (e.g. `LOG_INFO`, `_ORDER_NOT_FOUND`).

## Type Annotations

- Use native syntax (Python 3.11+): `X | None`, `list[X]`, `dict[K, V]`.
- Avoid `Optional[X]`, `List[X]`, `Dict[K, V]` from `typing`.
- Only import from `typing` what has no native equivalent: `Any`, `Callable`, `ClassVar`.
