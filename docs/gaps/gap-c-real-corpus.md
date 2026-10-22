# Gap — C 真实语料接入与误报基线（ROADMAP「C 语言包」阶段 5 剩余 / PROGRESS 退出判据 5）

- 状态：**未立项**（2026-10-21 调查轮 #43 交付：现状实测 + 方案 + 判据草案；实现分 #44/#45 两轮）
- 关联：`ROADMAP.md`「C 语言包」阶段 5；`PROGRESS.md` 退出判据 4/5；`tests/e2e/eval_diag_baseline.py`（verilog 先例）
- 参照：verilog 真实语料 `tests/e2e/samples/real/`（`CREDITS.md` + 工程分组 + 基线 JSON + `tests/policy/test_diag_baseline.py`）

## 目标

把"**真实 C 语料**上的诊断计数"固化成门禁：增长即失败（要么修规则、要么显式更新基线并说明
原因），使 C 包误报面不再靠人工偶然发现。口径与 verilog 先例同构——**只许减不许增**
（`eval_diag_baseline.py` 的 `compare` 语义）。

## 现状（本轮实测；语料只下载到临时目录，未入库）

**候选语料**（许可友好、体积可控，合计 ~250KB）：

| 语料 | 许可 | 规模（本轮实测） |
|---|---|---|
| cJSON（`cJSON.c` 3206 行 + `cJSON.h`） | MIT | 97KB |
| zlib：`adler32.c` 164 / `crc32.c` 983 / `gzread.c` 668 / `zutil.c` 313 / `compress.c` 99 / `uncompr.c` 101 | zlib license | ~130KB + 头文件 |

**harness 前置**（实测必需，缺一即不可达）：

1. 库头文件（`zlib.h`/`zconf.h`/`zutil.h`/`gzguts.h`、`cJSON.h`）随语料入库；
2. **最小系统头 stub** 12 个（`stdio.h`/`stdlib.h`/`string.h`/`math.h`/`limits.h`/`float.h`/
   `ctype.h`/`locale.h`/`stddef.h`/`stdarg.h`/`stdint.h`/`stdbool.h`——只放语料用到的 typedef/原型，
   头注"仅供语料 harness，不是 libc 实现"）；
3. `include_dirs` 指向上两者。C 包声明 `include.on_missing = "error"` ⇒ **缺 include 是硬错误**
   （`tpc lint` 直接退出），不能靠"无异常"口径绕过。

**实测结果**（语料探针 = `scan_directives → expand_tokens → parser/linter`，与管线同路；
"#43" = 修 G1/G2 之前，"#44" = G1/G2 收口后，"#45" = G3 收口后）：

| 文件 | parser 截断（#43 → #44 → #45） | linter `phase-statement`（#43 → #44 → #45） |
|---|---|---|
| `cJSON.c` | 截断 → 截断 → 截断 | 124 → 56 → **56** |
| `zutil.c` | 截断 → 截断 → 截断 | 86 → 27 → **7** |
| `crc32.c` | 截断 → 截断 → 截断 | 45 → 14 → **4** |
| `adler32.c` | 截断 → 截断 → 截断 | 43 → 13 → **3** |
| `gzread.c` | 截断 → 截断 → 截断 | 40 → 10 → **0** |
| `compress.c` | 截断 → 截断 → 截断 | 36 → 12 → **6** |
| `uncompr.c` | 截断 → 截断 → 截断 | 35 → 11 → **5** |

#45 后 zlib 族剩余截断/误报**全部由 G4（typedef 名强转，需符号表/切片 1b）解释**；
cJSON 不变（其函数体 `(cJSON*)` 强转是 G4 主体）。G1/G2/G3 无残留。

⚠ 这批诊断是合法代码上的误报（oracle：gcc 16.1.0 编译同语料无错），**不是** verilog 先例
那种"已裁决的真诊断基线"。⇒ 直接按当前计数固化基线（门禁方案 B）会把误报制度化，只应作过渡。

> ⚠ **#43 报告更正**：`ProjectChecker` 结果里的 `parse_ok` 字段**不反映解析截断**（部分 AST 也算
> True）。判"解析是否完整"要用 `parser._parse_truncated`（或 linter 诊断）；上表按更正后的口径。

> 口径注：数字来自临时探针（语料在 `%TEMP%`，未入库），复现形态 =
> `scan_directives → expand_tokens → parser/linter`；入库后以 `eval_diag_baseline_c.py --json`
> 为唯一口径。行数用 `wc -l` 可复核。

## 根因（语法面）与收口状态

| # | 最小复现（`typedef int T;` 前置） | 失败位点 | 状态 |
|---|---|---|---|
| G1 | `extern T *p;` / `static T v;` / `const T *p` 在声明 / 成员 / 形参 / 函数定义 / for 初值 / `sizeof` 类型名位 | 说明符序列（typedef 名在存储类/限定符之后） | ✅ **#44 已收口** |
| G2 | `int * const q;` / `const char * const s` | Pointer 缺类型限定符列表（C99 §6.7.6） | ✅ **#44 已收口** |
| G3 | `void f(void *, size_t);` | ParamDecl 无法表达"只有 `*`、无名"的**抽象声明符** | ✅ **#45 已收口**（`@Pointer` / `@TypedefAbstractDeclarator` 两支；语料原型诊断清零） |
| G4 | `(cJSON*)` / `(Bytef *)` | `CastTypeName` 刻意不含 `@TypedefName`（强转的 typedef 歧义位，需解析前符号判定） | ❌ **未收口**：cJSON 剩余主体；调查/方案见 `gap-c-typedef-cast.md`（推荐 parser 内符号表，待拍板） |

**G1 成因**：C 说明符序列里「typedef 名」只挂在**首个说明符位**（`TypeSpecifier` 的一个分支）；
`SpecRest`（其余说明符）**刻意不含 `@TypedefName`**——它是贪婪重复，含进去会把声明符名吃掉
（`int x;` 的 `x` 被当类型名）。于是「存储类/限定符在前、typedef 名在后」整条无产生式可匹配。
**#44 修复** = 宿主声明符位「**声明符优先**」交替：先按既有 `@DeclaratorList`/`@Declarator` 读
（既有形态逐字不变），失败再读「一个 `@TypedefName` + 声明符」（`TypedefDeclarators` /
`TypedefDeclarator` / `TypedefInitDeclarator` 三个包装规则，节点绑定仿被包装规则的消费面）；
不需要符号表、不改既有 FIRST/候选注册，`_Atomic(int) x;` 这类"限定符本身就是类型"因第一支
已成功而不受第二支影响。**G2 修复** = `@Pointer` 加 `@TypeQualifier*`。
判据：`tests/languages/c/test_c_declaration_spec_order.py`（30 例：6 宿主 + 指针限定符 +
普通声明回归 + 符号收集 + 过接受边界；注释保留见「已知边界」#3）。

**#44 对抗审计补充**（独立审计员在提交后复核，3 项成立并已修/登记）：
- **A（已修）**包装规则最初用 `direct = "$2.direct"` 透出声明符子树 ⇒ `iter_children`
  走两遍（重复符号记录 + TAG001 假阳性）。修法 = 只绑 `declarator`，`FuncDef`/`ParamDecl`
  的 `name_path` 改为**候选路径列表**（语言包声明面）。
- **B（登记未修）**声明符优先交替的回滚不回收**注释簿记**（锚点集/行尾台账是增删混合操作），
  第二支成功时 typedef 名后的注释（行尾 / 独占行）可能被全局去重吞掉。**试修结果** =
  把行尾台账/锚点集纳入快照事务回滚：C 形态可保注释，但触发 **verilog 注释恢复回归**
  （`tests/e2e/test_comment_restore.py` 幂等失败——端口注释位置漂移/重复；锚点通道与既有
  领取/渲染机制协同复杂）⇒ 已回退，边界登记见下「已知边界」#3，修法另立项。
- **C（登记，不修）**交替第二支只按 token 形态判 typedef 名（无符号表），产生**过接受**
  （`int a b;` / `unsigned T x;` / `sizeof(int T)`，见下「过接受边界」）。

## 语法面方案（已定：循环 #44 采用 B）

- **B（已实施）**：如上「声明符优先」交替 + 指针限定符。语言包为主体；**另有引擎侧小改动**
  = 注释簿记事务化（对抗审计 B；解析快照记账，不是语法/语义机制）。`tests/languages/c` 全量
  零回归，真实语料误报按上表下降。
- **A（否，留档）**：引擎 `pre_scan` 驱动的 typedef 名 token 重定型（新增契约键 `retype`，
  与语言包既有 `type_name`/`trial_as` 同族）。否因：① **只解 G1**（G2/G3/G4 照旧）；
  ② 与将来切片 1b 的符号感知机制重复投入；③ 引擎契约面新增 + 全语言回归面。
  **复议触发** = 出现 ≥2 处"符号敏感位置"都需要语法层判断，或切片 1b 的符号机制落地后可顺手覆盖。
- **C（否）**：仅修 linter 侧分类不改语法——parser 仍截断，真实语料门禁会把"部分 AST"
  当现状固化；否。

## 已知边界（#44 对抗审计登记；不是修复目标）

1. **过接受（交替第二支无符号表）**：`int a b;`（漏逗号 → 读成「类型 a + 声明 b」）、
   `unsigned T x;`（两个类型说明符）、`sizeof(int T)` 会被接受且 linter 0 诊断。C 本身不
   允许这些形态 ⇒ 代价是 linter 失去"声明符间漏逗号"检出（旧行为：parse 截断 +
   `expected ';'`）。**升级触发** = 真实语料出现该类形态的误报（需符号表，属切片 1b）。
   判据锁定：`TestKnownOverAcceptanceBoundaries`（锁"当前接受"，边界消失即红——防静默漂移）。
2. **渲染边界（既有，非 #44 引入）**：行终止注释落在**展平行内**的声明符/说明符之间时，
   LineSuffix 在原子节点边界就地落地、可能吞后续 token（`struct S { int // c\nx; };`
   → `int // c x;`，**旧语法同坏**；`const T // c\n*p;` 变体同样）。修复 = 渲染器让行终止
   LineSuffix 跨节点延迟到全局换行点（另立项，TODO 1.2）。#44 判据只锁"注释不丢（不重复）"，
   **不锁该形态的渲染正确性**；触发 = 真实语料命中该形态。
3. **新形态注释可能在交替回滚中丢失（#44 审计 B；登记未修）**：`extern T // c\nv;`、
   `extern\n// c\nT *p;` 这类「说明符之间注释 + typedef 名后置」形态，注释可能在声明符
   优先交替的回滚中被去重吞掉（旧形态同位置保留）。修复尝试 = 注释簿记事务化
   （行尾台账/锚点集进快照），C 形态可行但**触发 verilog 注释恢复回归** ⇒ 回退。
   修法（另立项，TODO 1.2）：事务化簿记 + 原子节点领取/渲染面协同（需同时处理
   `_claim_head_comments` 对原子 `ref` 布局节点的领取）。
   触发 = 真实语料出现该形态；#44 判据**不含**注释保留断言。

## 门禁时序方案（A / B / C）

- **A（推荐）先修语法/误报再上门禁**：G1/G2 已收口（#44）；**G3/G4 收口后**才能让 7 文件
  `_parse_truncated=False` 并落 baseline 门禁（G4/切片 1b 是最大前置）。理由：门禁价值 =
  防增长；基线全是误报时增量判据被噪声淹没，且"合法代码被报"被写成现状。
- **B（过渡，按需）**：以当前计数为基线、只卡增长。可立刻防回归，但要求档内显式声明
  "基线里 N 条是待清偿误报"，并逐轮降基线；**不得当结论口径**。
- **C（否）**：只用当前零误报的合成语料（`ring_buffer.*`）——不满足"真实"要求；否。

## 判据草案（门禁实现轮用；可执行形态）

**前置**：G3（未命名抽象指针形参）+ G4（typedef 强转，切片 1b）→ 7 文件解析完整后，下列
sanity 才可达；在此之前只能按门禁方案 B 过渡或等前置。

1. **语料入库**：`tests/e2e/samples/real_c_ref/`——cJSON 2 文件 + zlib 6 文件与所需头；
   `CREDITS.md` 按 verilog 先例记 **来源仓库 + 版本/commit + 许可**（zlib license、MIT）；
   `stubs/` 12 个最小系统头（各文件头注"语料 harness 专用，非 libc"）。
2. **采集器**：`tests/e2e/eval_diag_baseline_c.py`——`collect()` 用
   `ProjectChecker(rules_dir="grammar/c", ext_dirs=None, include_dirs=[ref, stubs])` 逐文件/分组
   check，计 `{code: 条数}`（syntax 前缀 + semantic 两族，同 verilog 口径）；
   `compare/load/write` 复用或抽出参数化实现（避免第二份口径）。
3. **基线文件**：`tests/e2e/samples/real_c_ref/diag_baseline.json`（`_note`/`corpus`/`total`/`counts`）。
4. **门禁**：`tests/policy/test_diag_baseline_c.py`——增长 ⇒ fail；减少 ⇒ pass（提示可刷新）；
   `total` 自洽；基线非空；**语料 sanity = 每文件解析完整**（判据用 `parser._parse_truncated
   is False`，**不是**结果 dict 的 `parse_ok` 字段——后者不反映截断，见上「报告更正」；
   verilog 侧同型教训见 `tests/e2e/test_real_corpus.py`）。
5. **确定性**：同语料两次 `collect()` 键值相同（防集合序/哈希序漂移）；单次目标 ≤ 30s
   （探针实测 ~2s/文件，含 include 展开）。
6. **测量面**：门禁只卡诊断计数；"parse 率 / 零误报"作为前置过程判据，不进门禁。
7. **#44 已落判据**（前置之外的回归面）：`tests/languages/c/test_c_declaration_spec_order.py`
   30 例——6 宿主 × {解析完整 / linter 0 / 渲染 token 相同 / 幂等}、指针限定符、普通声明回归、
   符号收集单条记录（审计 A）、过接受边界（审计 C）。

## 预算与止损

- #43 调查轮：自定 ≤8 条命令，实际 7 文件 + 2 类最小复现（超出 1 次，已记录）。
- #44 实现轮：≤10 条探针命令（实际 ~8：原型 3 + 实现后 5）；实测面 = 既有 C 包全量
  （1078 例）+ 新判据 24 例 + 真实语料计数。
- **止损点**：G3+G4 收口后若仍有 >20 条/文件且无法归类 ⇒ 语料收窄为"可零误报子集"并在本档
  登记未收口类别，**不硬上基线**（避免门禁方案 B 的误报固化）；不得以"基线非空"冒充达标。

## 决策点

- **下一轮 #45**：G3（未命名抽象指针形参）实现级自决（语言包形态改动，不碰引擎）。
- **G4 / 切片 1b**（typedef 名强转需符号表）：属 ROADMAP 已登记方向，时机由作者排期；
  它是真实语料门禁（退出判据 5）的**最大前置**。
- 语料入库时机：G3/G4 后（否则 sanity「解析完整」不可达）。
- 细节级自决（无需作者）：stub 内容、文件分组、预算数字、采集器去重方式。

## 关联条目

- `docs/gaps/gap-language-pack-scope.md`（C 包接受域现状 / 门禁清单）
- `docs/gaps/gap-parser-linter-approximation.md`（linter 近似的同族缺口）
- `tests/e2e/eval_diag_baseline.py`、`tests/policy/test_diag_baseline.py`（verilog 先例）
- `ROADMAP.md`「C 语言包」阶段 5、`PROGRESS.md` 退出判据 5
