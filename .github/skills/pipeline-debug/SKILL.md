---
name: pipeline-debug
description: '调试解析管线故障：从 Token 流到 AST 再到渲染产物，逐步定位解析/渲染失败的原因。适用于新增用例解析失败、生成代码错位等问题。'
user-invocable: true
argument-hint: '指定测试用例名，如 led_blinker'
---

# Pipeline Debug — 管线调试

## 适用场景

- 新增测试用例解析失败（parser 返回 None 或 AST 节点异常少）
- 生成代码出现语义错位（如注释合并、缩进错误、缺失节点）
- 修改规则后某用例从通过变为不通过
- 需要排查 parser warning 的根因

## 快速诊断

```bash
# 基础诊断报告
python .github/skills/pipeline-debug/scripts/diagnose.py <test_name>

# 带详细输出
python .github/skills/pipeline-debug/scripts/diagnose.py <test_name> --verbose

# 跳过渲染阶段（仅排查解析）
python .github/skills/pipeline-debug/scripts/diagnose.py <test_name> --no-render

# 追踪某个 Token 的候选规则（排查 "所有候选规则匹配失败" 时用）
python .github/skills/pipeline-debug/scripts/diagnose.py <test_name> --trace-token keyword.reg
```

诊断报告包含：
- Token 数量与 Token 流前 20 条
- 规则总数和 statement 规则数
- Parser 警告列表
- AST 节点数（原始 / 归一化后）
- 渲染产物预览

## 分步调试流程

### 第 1 步：Token 流 — 确认词法分析是否正确

Token 流是解析的输入，如果 Token 类型错位或缺失，后续分析必然失败。

**检查要点：**
- Token 数量是否符合预期
- 关键字 Token 是否正确识别（如 `keyword.module`、`keyword.always`）
- 是否有意外的 `newline` 打断了预期的 Token 序列
- `id` 类型是否正确（标识符是否被误识别为关键字）

**常见问题：**
```
# Token 间 unexpected newline — 可能缺少续行处理
# id 被识别为 keyword — 检查 _token.toml 关键字列表
```

### 第 2 步：Parser 警告 — 定位规则匹配失败

Parser 的 `parse_sentence` 在候选规则全部匹配失败时会输出 `⚠️ [解析器] 所有候选规则匹配失败`。

**检查要点：**
- 哪个 Token 触发了警告？
- 该 Token 的候选规则有哪些？（查看 `start_token_map`）
- 候选规则为什么全部失败？

**候选规则分析逻辑：**

1. 查询 `start_token_map[token_type]` 获取候选规则列表
2. 候选规则按 `statement_rule_names` 顺序排序（`rule_selector.py:153`）
3. 每个候选规则依次尝试，直到匹配成功
4. 如果全部失败，`parse_sentence` 返回 None，`parse_block_body` 退出循环

**常见失败原因：**
- **$N 越界**：节点映射引用不存在的产生式序号
- **end_case 不匹配**：规则匹配成功后，当前 Token 不在 end_case 列表中
- **inline 规则多属性**：多个属性映射导致 inline 扁平化异常
- **产生式第一个 Token 不匹配**：规则的第一个产生式元素无法匹配当前 Token

### 第 3 步：AST 结构 — 检查解析结果拓扑

AST 节点数能快速反映解析是否正常：

| 节点数 | 含义 |
|--------|------|
| 1（仅 Root） | 解析几乎完全失败 |
| < 10 | 只解析了顶层结构 |
| 正常（几十~几百） | 解析基本正常 |

**检查方法：** 对比原始 AST 和归一化后 AST 的节点数变化：
- 原始 AST 含 `optional`、`repeat`、`seq` 等包装节点
- 归一化后这些包装节点被消除
- 如果归一化后节点数急剧减少，说明包装节点太多

### 第 4 步：规则配置 — 逐级检查 Production

当某个 Token 有候选规则但匹配失败时，手工检查该规则的配置：

1. **production 数组长度** — 节点映射的 `$N` 不能超过此长度
2. **end_case 定义** — 规则匹配后需要检查的结束符
3. **inline 标志** — inline 规则只能有一个属性映射
4. **block_start / block_end** — 块规则是否需要起始/结束符
5. **atomic 标志** — atomic 规则在解析器中的特殊处理

### 第 5 步：Normalizer — 检查 AST 消除是否过度

Normalizer 会消除 `optional`、`repeat`、`seq` 包装节点。如果配置不当，可能会消除代表语法结构的必要节点。

**检查要点：**
- `optional` 消除后子节点是否丢失
- `repeat` 展开后列表是否为空
- `flatten_types` 中的配置是否过于宽泛

### 第 6 步：Renderer — 检查生成产物

如果解析正常但渲染异常：

1. **检查 Layout 配置**：TOML 中的 `layout` / `head` / `body` / `tail` 定义
2. **检查原始语：SoftLine/Line/Break** 的 flat/broken 选择
   - `SoftLine` 在 flat 模式转为空格，broken 模式转为换行
   - `Break` 始终换行（不受 flat/broken 影响）
   - `group` 包裹的内容可能被整体压成一行
3. **Nest 叠加效应**：多层缩进可能叠加导致多余空格
4. **对比参考文件**：ref/*.v 与 gen/*.v 逐行对比

## 典型问题

已知问题汇总在 `docs/debug_known_issues.md`，包含已修复问题的根因和修复记录，可供排查时快速对照。

## 项目管线结构

```
源文件 → Lexer → Parser → Normalizer → SemanticAnalyzer → Renderer → 生成代码
         ↑        ↑           ↑               ↑               ↑
      _token    rules_    normalize       TOML 语义        layout DSL
      .toml     *.toml   _config.toml     自声明           (head/body/tail)
```

当排查失败时，从前往后逐个阶段验证，能最快定位根因。
