# custom_rules_example — 自定义规则范例（照抄模板）

> 这不是产品规则集，而是"如何给 tpc 加自己的检查规则"的**可运行范例**。
> 两条规则各走一条路径，正好对应 `../README.md`「编写检查规则」的双路径实操。

## 两条规则

| 码 | 判定 | 路径 | 脚本 |
|---|---|---|---|
| EX001 | 模块使用非 ANSI 端口声明（旧式 body 端口） | L2 postpass（结构/整树） | `_ansi_header.py` |
| EX002 | parameter 使用 integer 类型 | L2 handler（单符号） | `rules/_param_type.py` |

两条规则 **`default = false`（默认关）**——启用前对诊断面零影响；
验收样本在 `tests/e2e/samples/check_accuracy/`（pos×2 + neg×1）。

## 路径怎么选（照抄前先判）

- 判定只看**符号名**（正则能写）→ L1 `pattern`（见 `../name_check`，零脚本）
- 判定要**单符号上下文**（声明形态/节点属性/文件上下文）→ L2 `handler`
- 判定要**整棵树 / 跨文件**（结构走查、模块联动）→ L2 `postpass`

## 照抄四步

1. 复制本目录 → 改组件名（目录名即组件名，需全 plugins 树唯一）
2. 语言包 `tpc.toml` 的 `[plugins] enabled` 加组件名
3. 规则码自定；`default = false` 起步（默认开关是数据决策：实测误报面后再定）
4. 配样本：`tests/e2e/samples/check_accuracy/cases/<CODE>_<主题>/`（pos 期望
   命中 + neg 干净），码进 `expected.json` 的 `focus`——规则自此进入评测与
   "规则可达性"门禁（`tests/policy/test_rule_coverage.py`）

## 启用方式

- 用户配置（P4）：`config/tpc_config.json` 的 `checks.enabled` 列出规则码
  （"不选即关"；缺省 = 规则表默认值，本范例默认关）
- 评测：`expected.json` 的 `focus` 列出即启用（评测专用注入）
- 覆盖/豁免：`checks.overrides`（severity 覆盖）/ `checks.per_file`（按文件豁免）

## 相关

- 双路径实操、context.extra 键、常见坑：`../README.md`「编写检查规则」
- 规则字段语义与规则表 schema：`analyzer/README.md` + `analyzer/checks.py`
