# Gap — 宏展开与诊断位置对应（(a) 行号映射 / (b) 宏归因）

- 状态：**立项中**（TODO「缺口闭环队列」②，2026-09-12 排队；切片见下「可实现性」）
- 关联：TODO.md「0.1.2 目标」节下的「检查链宏位置映射」条目
- 参照：`docs/decisions/0016-macro-body-into-ast.md`（raw 源区间权威 + 对应层）、
  P3.3 双向映射
- 实测：2026-09-12（下节「事实基础」均可复现）

## 缺口是什么

两条链对宏处理策略不同，各自都有明确理由（**不是遗漏**）：

| 链 | 展开 | 树 | 理由 |
|---|---|---|---|
| pipeline（format/expand） | `expand_tokens()` 默认（marker 保真锚） | raw 骨架 + `MacroCall` 壳 + `_macro_fragment`（渲染走源区间） | 保真：要还原 `` `M `` 原文 |
| analyzer/check | `expand_tokens(..., semantic=True)` | **宏体展开铺进文本**，按真实语法类别进树 | 可分析 |

实测（check 链 AST）：`` `define USEZ a = z; `` + `` always @* begin `USEZ end `` →
`BeginEnd > BlockingAssign > Identifier('a'), Identifier('z')`，**无 marker 残留**。
即 check 链**能分析宏体，无信息流失**（此处曾误判为"流失"，已实测推翻）。

但由此留下两个**位置信息**缺口：

- **(a)** 诊断行号基于**展开后**文本 → 多行宏体展开后行数增加，宏体附近的诊断
  行号与源文件偏移，用户按行号回源会定位错。
- **(b)** check 链**不感知宏**（`analyzer/**` 里 `MacroCall|tpc_marker|_macro_body`
  grep 为空）→ 诊断无法回答"这条来自宏 X"，不能按宏粒度抑制/归类，IDE 跳转与
  related 链也指不回宏调用位。

## 为什么是缺口（影响面）

- (a) 作者**已明示且有意推迟**——`analyzer/structure.py::_expand_source` docstring：
  「诊断行号基于展开后文本（宏 span 反向映射属 **P3.3** 范畴，**语义正确性优先**）」。
  所以它不是疏漏，是权衡：映射**可能不准**时，诚实的"展开后行号"优于错误的"源行号"。
- (b) 影响诊断可用性：宏密集工程（tv80 / darkriscv / ice40）里宏体触发的诊断
  无法定位到宏调用点，也无法"忽略某宏体内的问题"。

## 成熟解法参照（见贤思齐）

- 📌 **Clang**：「全展开 + 双位置 + 旁路记录表」——每个展开产出的 token 同时保留
  *spelling location*（源）与 *expansion location*（宏调用位）。本项目 ADR-0016
  决策第 5 条的「对应层（区间 ↔ 展开 ↔ 定义）」是同一思路的更轻形式。
- 🔥 **直接借鉴点**：不必给树打宏标记。诊断是**行级**的，只需产出
  「展开后行 → 源行」的映射表；**(b) 由 (a) 的表反查即可**（诊断落点落在哪个宏
  的展开区间 → 归因）。两项共用一份表，先做 (a) 则 (b) 近乎免费。

## 可实现性

### 事实基础（2026-09-12 实测）

- `preprocessor/_expand.py::expand_tokens` 是**逐行就地替换**
  （`lines[line_no - 1] = "".join(parts)`）→ 输出行偏移**只**由"宏体含多行"引起，
  用「源行 → 输出起始行」的 `list[int]` 累加即可，**不需要**完整区间表。
- `semantic=True` 分支目前是 `continue`（`_expand.py` L605-608）→ **不建任何锚**，
  这是 (a) 的前置改动点。
- 诊断产出**只有 2 处**（`analyzer/checker.py`）：`_syntax_diag`（取 `span[0].line`）
  与 `_semantic_diag`（取 `node._pos_line`）→ 接线集中。
- 回归面小：现有行号断言几乎不含宏（`test_linter_macro_hygiene` 走 raw 源、
  `test_lexer` 与宏无关）；`tests/e2e/samples/real/diag_baseline.json` 只记**条数**，
  不受行号影响。

### 切片（每片独立可验证）

1. **(a) 行级映射**
   - `expand_tokens(semantic=True)` 产出行映射（复用逐行结构）→ ~15 行
   - `_expand_source` 返回 `(clean, line_map)`；`FileResult` 存表 → ~8 行
   - 诊断 2 处换算 + **无法映射时保守回退**（保持展开后行号并标记）→ ~10 行
   - 测试：**形态覆盖是重心**——单行宏 / 多行宏 / 嵌套宏 / 带参宏 / 条件编译
     × 映射断言 → ~60 行
   - 验收：各形态行号正确 + 不可映射时明确回退 + 全量门禁绿
2. **(b) 宏归因**（依赖 (a)）
   - 诊断落点查 (a) 表 → 落在某宏展开区间则加 `"macro": "<NAME>"` 字段 → ~30 行
   - 独立做（不先做 (a)）需跨 lexer 锚 / parser 属性 / 遍历传递三部件 ~150 行
     → 不推荐

### 难点（真正的成本）

**映射准确性**：嵌套宏、条件编译多路径、带参宏实参替换都会让「输出行 → 源行」
不确定。而**不准的行号比诚实的展开后行号更糟**——用户会照着错位置改代码，且
看不出错。所以必须保守回退（不确定即标注"不可映射"），并把形态覆盖测试当验收
重心。**成本主要在测试，不在代码。**

### 边界

- 不做列级（`character`）：诊断主要看行；列级需更细映射、成本跳一档，按需再议。
- 不动 `semantic=True` 的展开语义（宏体仍铺进文本）——本缺口只补位置信息。

## 关联条目

- 决策：`docs/decisions/0016-macro-body-into-ast.md`（raw 源区间权威 + 对应层）
- 前置/后续：P3.3 双向映射（ADR-0016 关联节）
- 代码：`preprocessor/_expand.py::expand_tokens` /
  `analyzer/structure.py::_expand_source` / `analyzer/checker.py::{_syntax_diag,_semantic_diag}`
- 同族缺口：`gap-preprocessor-macro-boundaries.md`（**宏覆盖**缺口——哪些宏形态
  没支持；本档是**已支持形态的位置信息**缺口，问题不同，不要合并）
- 实测记录：`/memories/repo/confidence.md` 2026-09-12 两条
