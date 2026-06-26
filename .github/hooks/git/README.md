# Git Hooks

本目录包含 Git 钩子脚本，通过 `core.hooksPath` 配置启用。

## 启用

```bash
git config core.hooksPath .github/hooks/git
```

配置后全局生效（仅当前仓库），钩子会被提交到仓库共享给团队。

## 可用钩子

### post-commit

每次提交后自动更新 `session-summary.md` 中的日期和分支 SHA。

### commit-msg

校验提交信息格式：

```
type(scope): description

# 示例
feat(parser): add for-loop support
fix(renderer): correct port indentation
refactor(lexer): extract number FSM
```

允许的 type: `feat`, `fix`, `refactor`, `style`, `test`, `docs`, `chore`, `perf`, `ci`

scope 可选，首行不超过 72 字符。
