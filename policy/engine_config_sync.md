# 引擎语义变更的配置同步规程

> 动机：引擎语义/键名一改（如换行三态化），"语言包配置哪些点位要跟着改"当前
> 只能逐个 TOML 人工翻——改造面不确定、易漏、旧错键静默留着。本规程把它变成
> 机械过程（工具：`tools/config_sites.py`）。
> 制度由工具执行；词汇表维护点见工具内的 `_VOCAB_*`。

## 四步（"翻译"式）

| 步 | 动作 | 机械依据 |
|---|---|---|
| 1 | 定位语言包 | `grammar/*/tpc.toml` 即语言包根（含其下组件目录递归） |
| 2 | 取配置字典 | 扫描 TOML 文本：跟踪 `[段]` 路径 + 行内表 `{k = v}` 嵌套，记录 `file:line` / 段路径 / 原值 |
| 3 | 关键字匹配 | 按**整键相等**比对——`break` 不命中 `break_distance`，`soft` 不命中 `first_soft`/`no_soft`（子串误伤是这类改写的主要坑） |
| 4 | 逐项替换 | 只换键 token 本身（值/注释/排版不动），默认 dry-run，核对后 `--apply` |

## 命令

```bash
python tools/config_sites.py list --renderer-only          # 渲染段全量点位（按键聚合）
python tools/config_sites.py list --key break --renderer-only   # 单键点位（file:line）
python tools/config_sites.py check                          # 配置漂移哨兵（见下）
python tools/config_sites.py rename --from break --to hard_break --value true --renderer-only
python tools/config_sites.py rename ... --apply             # 确认后再写入
```

## 引擎侧纪律

- **改渲染段键名/语义前**先 `list --key <旧键>` 拿到改造面，再 `rename`，
  再跑门测（`pytest -m smoke` → 全量）——**不逐个 TOML 手翻**。
- **`check` 是配置漂移哨兵**：渲染段出现引擎词汇表以外的键 = 拼写错 / 机制已删
  的残留 / 未登记的机制。结构键（`override.<Rule>` 下的规则名、容器键）由位置
  豁免，不误报。
- **词汇表维护点**：`tools/config_sites.py` 的 `_VOCAB_DISPATCH` / `_VOCAB_ELEMENT` /
  `_VOCAB_SECTION`——引擎改键名时先同步这里（否则 `check` 会把新键误判为漂移）。
  原语 dispatch 键从注册表运行时读，不重复声明。

## check 的两条规则

1. **非引擎词汇键**：渲染段出现词汇表以外的键（拼写错 / 机制已删残留）。
   结构键豁免：`override.<Rule>` 下的规则名、容器键（值为 `{`）。
2. **多原语键同层（静默失效）**：同一行内表写了多个原语 dispatch 键时，只有
   **注册顺序最前**的生效（`renderer/primitives/__init__.py::eval_expr`），
   其余连同其子树**静默失效**——“看着改了其实没生效”。
   - 例外：`line` 数组元素由 `eval_line` **内联**消费（`{soft}`/`{break}` 不走
     dispatch，可与 `indent` 共存），不参与本检查。
   - 实测（2026-09-17）：`ModuleDecl.renderer.head` / `MacroModuleDecl.renderer.head`
     的 `{ opt = { group = [...], ref = "ports" } }` 中 `ref`（注册序 0）遮蔽
     `group` → 其内 `{ break = true }`（端口后、`)` 前）**从未求值**——这是
     “新行语义三态化（M1）”必须先清的前置：不能建在死配置上。

## 门禁地位

`check` 暂列**开发自查工具**（不进日常门禁）：普通开发不碰配置键时跑它无收益；
**改动渲染段配置或引擎键名时必须跑**。若后续出现"配置漂移漏改"类事故，按
`policy/README.md` 的门禁升格流程提为 gate。
