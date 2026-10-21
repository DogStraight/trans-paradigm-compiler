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

**实测结果**（`ProjectChecker(rules_dir="grammar/c", include_dirs=[语料, stubs])`，逐文件）：

| 文件 | parser | linter `phase-statement` |
|---|---|---|
| `cJSON.c` | 接受（AST 非空） | **124** |
| `zutil.c` | 接受 | 86 |
| `crc32.c` | 接受 | 45 |
| `adler32.c` | 接受 | 43 |
| `gzread.c` | 接受 | 40 |
| `compress.c` | 接受 | 36 |
| `uncompr.c` | 接受 | 35 |

⚠ **这批诊断是合法代码上的误报**（oracle：gcc 16.1.0 编译同语料无错），**不是** verilog 先例
那种"已裁决的真诊断基线"。⇒ 直接按当前计数固化基线（方案 B）会把误报制度化，只应作过渡。

> 口径注：上表数字来自本轮**临时探针**（语料在 `%TEMP%`，未入库），复现形态 =
> `scan_directives → expand_tokens → parser/linter`（与管线同路）；入库后以
> `eval_diag_baseline_c.py --json` 为唯一口径。行数用 `wc -l` 可复核。

## 根因（已定位的两类，最小复现 = parser 接受 / linter 报错）

1. **typedef 名作类型 + 存储类 + 指针**：
   `typedef int T;\nextern T *p;\n` → linter 1 条 `expected ';' got 'symbol.base.multiple'`
   （`extern const T *p;` 同）。真实语料命中：zlib 的 `ZEXTERN`（展开为 `extern`）+ `Bytef *`。
2. **双 const 指针参数**：
   `typedef struct S S;\nint f(const S * const p);\n` → linter 2 条
   （`unexpected '('` + `expected ';' got 'keyword.const'`）。真实语料命中：cJSON 55 处
   `const cJSON * const item`。

两类都在 **linter 反解析器**（`phase-statement`），parser 侧正常；与
`docs/gaps/gap-parser-linter-approximation.md` 同族（启发式近似）。⚠ 上表 `(` / `id` /
`keyword.const` 等类别**未穷尽归因**——#44 需逐类收敛，本档只给已复现的两条最小样本。
复现命令（临时）：

    python -c "…ProjectChecker(rules_dir='grammar/c', include_dirs=[…]).check('cJSON.c')"

## 方案（A / B / C）

- **A（推荐）先修 FP 再上门禁**：`#44` 把 linter 两类 FP 修到"语料零误报（或仅剩显式登记的
  已知边界）"，`#45` 再落 baseline 门禁。理由：门禁价值 = 防增长；基线全是误报时增量判据被
  噪声淹没，且"合法代码被报"被写成现状。
- **B（过渡，按需）**：以当前计数为基线、只卡增长。可立刻防回归，但要求档内显式声明
  "基线里 N 条是待清偿误报"，并逐轮降基线；**不得当结论口径**。
- **C（否）**：只用当前零误报的合成语料（`ring_buffer.*`）——不满足"真实"要求；否。

## 判据草案（#45 实现轮用；可执行形态）

1. **语料入库**：`tests/e2e/samples/real_c_ref/`——cJSON 2 文件 + zlib 6 文件与所需头；
   `CREDITS.md` 按 verilog 先例记 **来源仓库 + 版本/commit + 许可**（zlib license、MIT）；
   `stubs/` 12 个最小系统头（各文件头注"语料 harness 专用，非 libc"）。
2. **采集器**：`tests/e2e/eval_diag_baseline_c.py`——`collect()` 用
   `ProjectChecker(rules_dir="grammar/c", ext_dirs=None, include_dirs=[ref, stubs])` 逐文件/分组
   check，计 `{code: 条数}`（syntax 前缀 + semantic 两族，同 verilog 口径）；
   `compare/load/write` 复用或抽出参数化实现（避免第二份口径）。
3. **基线文件**：`tests/e2e/samples/real_c_ref/diag_baseline.json`（`_note`/`corpus`/`total`/`counts`）。
4. **门禁**：`tests/policy/test_diag_baseline_c.py`——增长 ⇒ fail；减少 ⇒ pass（提示可刷新）；
   `total` 自洽；基线非空；**语料 sanity = 每文件 `parse_ok=True`**（防"解析失败 ⇒ 0 诊断"假绿；
   verilog 侧同型教训见 `tests/e2e/test_real_corpus.py`）。
5. **确定性**：同语料两次 `collect()` 键值相同（防集合序/哈希序漂移）；单次目标 ≤ 30s
   （本轮 7 文件实测 ~2s/文件，含 include 展开）。
6. **测量面**：门禁只卡诊断计数；"parse 率 / 真实语料零误报"作为 #44 的过程判据，不进门禁。

## 预算与止损

- 调查轮探针上限（本轮自定）：≤8 条命令 / ≤3 候选工程；**实际**：下载 cJSON+zlib、
  7 文件实测、2 类最小复现（超出 1 次，如实记录）。
- **止损点**：若 #44 修完两类 FP 后仍有 >20 条/文件且无法归类 ⇒ 语料收窄为"可零误报子集"
  并在本档登记未收口类别，**不硬上基线**（避免方案 B 的误报固化）；不得以"基线非空"冒充达标。

## 决策点（#44 开工前定）

- 语料选型：cJSON + zlib 子集是否入库（许可 OK、体积 ~250KB ≪ verilog 580KB；建议入库）。
- 口径：是否走 B 过渡（建议否，按 A 分两轮）。
- 细节级自决（无需作者）：stub 内容、文件分组、预算数字、采集器去重方式。

## 关联条目

- `docs/gaps/gap-language-pack-scope.md`（C 包接受域现状 / 门禁清单）
- `docs/gaps/gap-parser-linter-approximation.md`（linter 近似的同族缺口）
- `tests/e2e/eval_diag_baseline.py`、`tests/policy/test_diag_baseline.py`（verilog 先例）
- `ROADMAP.md`「C 语言包」阶段 5、`PROGRESS.md` 退出判据 5
