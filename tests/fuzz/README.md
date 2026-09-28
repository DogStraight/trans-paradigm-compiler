# Fuzz / 差分 / 边缘构造验证（tests/fuzz, tests/edge, tests/differential）

> 动机（原 docs/known_limitations.md 边界，2026-09-04 拆入
> `docs/gaps/gap-verification-engineering.md`）："Validation is sample-driven,
> not exhaustive… no fuzzing, property-based, or differential testing yet"——
> 本目录补齐这三块。
> 语法是数据 → fuzzer 直接从 grammar TOML 驱动，无需手写生成器。

## 目录

| 目录 | 内容 | 运行 |
|---|---|---|
| `tests/fuzz/` | 语法驱动生成 + 变异 fuzzing，断言不变量；**回馈链路**（最小化 + 沉淀） | `python tests/fuzz/run_fuzz.py --iters 800` |
| `tests/edge/` | 边缘构造门禁（clean 必须成功 / reject 必须失败 + 抬头登记的不变量复检） | `python tests/edge/run_edge.py` |
| `tests/differential/` | 与 verible-verilog-format 对拍（可选依赖） | `python tests/differential/run_differential.py` |

## 回馈链路（fuzz 发现 → 最小复现 → 回归）

四环闭环，**后两环（最小化 / 沉淀）已自动化**：

```
[1] 生成/变异          python tests/fuzz/run_fuzz.py --iters 800 [--pack grammar/c]
        │                 → findings/*.v + findings/index.jsonl（机器可读：类别/标签/包）
[2] 判据（oracle.py）   不变量五类，run_fuzz 与 shrink **共用同一份**（判据一变，
        │                 缩出来的就不是原来那个 bug）
[3] 最小化（ddmin）     python tests/fuzz/shrink.py --all [--pack grammar/c]
        │                 → findings/min/*.v（行级 ddmin + 尾截 + 行内字符级）
[4] 沉淀                python tests/fuzz/shrink.py --all --sediment tests/edge/edge_corpus \
        │                    --cause "根因一句话" [--name 语义名]
        │                 → edge_corpus/{clean,reject}/<name>.v（最小复现 + 溯源抬头）
        └─ 门禁            python tests/edge/run_edge.py
```

**时序要点（两处闸）**：最小化只在缺陷**还活着**时做得动（判据 = 仍触发同一类别）；
沉淀只在缺陷**已修**时才允许写。故正常节奏是：

1. 发现后先 `shrink.py --all`（此时缺陷活着）→ 留下最小复现；
2. 修；
3. `shrink.py --all --sediment <dir> --cause "…"`（此时类别已不复现）→ 沉淀成回归；
4. `run_edge.py` 复核。

两个方向都被闸守着，实测过：
- **未修不许沉淀**：类别仍在复现 → 拒绝（写进去等于把缺陷固化成期望行为）。
  判别性用例是 `success=True` 的那类（非幂等）：只按 clean/reject 判会一路写进 `clean/`。
- **已修不再最小化**：类别不复现 → 直接走沉淀（避免"活着的被拒、修完的被跳过 ⇒
  永远沉淀不了"）。

## 语言包

`--pack <dir>` 一处指定，**生成器 / 词法 / 管线 / 种子**随之（缺一就会"用 A 包生成、
用 B 包格式化"，产出的 finding 全是假的）。非默认包默认种该包自己的样本：

```
python tests/fuzz/run_fuzz.py --pack grammar/c --iters 4000      # C 包（首轮实测 0 findings）
python tests/fuzz/shrink.py --all --pack grammar/c
python tests/edge/run_edge.py --corpus tests/edge/edge_corpus_c --pack grammar/c
```

⚠ C 包未声明 `capability.formatter`（其"格式化"就是声明式渲染布局），故 fuzz 只走
渲染面，`[formatter] skipped` 的 stderr 提示属正常。

## 沉淀语料的抬头纪律

自动沉淀写出的抬头（也是 `run_edge.py` 的复检登记项）：

```
// edge reject（fuzz 回归 2026-09-26）: <根因一句话（--cause 给）>。
// fuzz 类别 <kind>；原 finding <file>；最小复现 86→81 字节 / 2→1 行；修复后必须失败。
```

- 抬头里的**类别**从此成为这条语料的不变量判据（`run_edge.py` 复检）——
  只断言 clean/reject 挡不住"仍非幂等"这类 `success=True` 的活缺陷；
- **判定必须与所在目录一致**、**不得留 `成因待补`**：由
  `tests/policy/test_edge_corpus_provenance.py` 守（2026-09-26 起要求类别项；
  此前 4 条手工沉淀豁免——它们的失败模式当时还没有类别名，硬凑类别是造假）。

## 不变量（fuzz oracle，定义在 `oracle.py`）

| 类别（kind） | 判据 |
|---|---|
| `crash` | 管线抛异常（硬违规） |
| `silent-fail` | `success=False` 且无 error |
| `tokenize-fail` | 合法输入格式化后不可 token 化 |
| `token-corrupt` | 格式化改变了非 trivia token 序列（仅 `gen` 标签） |
| `idem-crash` | 二次格式化崩溃 |
| `non-idempotent` | `format(format(x)) != format(x)` |

## 已知的 oracle 判定（良性偏差类）

- **module 头规范化**：`module m`（无括号）→ 渲染为 `module m();`（渲染器
  恒输出 `(...)`）。语义无害（空括号 ≈ 无端口），但违反严格 token 保序——
  变异 fuzzer 会产出此类发现，属低严重度、已知行为，不是内容丢失
  （README 顶层同记录）。
- **畸形输入容错重构**：mutation 产物的容错解析会补分号/重构结构（如
  `module m m ;` → `module m; m;`）——畸形输入不在"不改内容"契约内，
  TOKEN-CORRUPT 检查跳过 mutation 样本（保留不崩溃/幂等检查）。
- 判定方向：**token 丢失（in > out）是硬违规**（静默删代码）；token 增加
  （out > in）需人工确认（多为规范化）。
- **C 包注释折行漂移（`non-idempotent`，2026-09-26 定案不修）**：分隔符后行尾注释跨折行
  时落位漂移（`int first /* x×60 */, second;` → 首遍与次遍输出不同，第三遍起收敛）。
  作者决策 = **不修渲染，归原始路径（raw）解决**（理由与先例见
  `docs/gaps/gap-language-pack-scope.md` 渲染现状表 #6）。故它**永久留在"活缺陷"一侧**：
  按"未修不许沉淀"的闸不进 `edge_corpus`——这是**已知且接受**的偏差，不是待修项；
  跑 fuzz 遇到它时按已知类处理（不新增登记）。

## 最小化算法（为什么是 ddmin）

单元取**行**（文本输入的自然粒度）+ 行内字符级，判据是"仍触发同一**类别**"
（不比 detail——它含计数，会随收缩变化）。算法取 Zeller & Hildebrandt 的
**ddmin**（块删除 + 只保留块两路，IEEE TSE 2002）：对"大部分内容与失败无关"
的输入，比逐行删除快一个量级。

实测（C 包非幂等个案，86 字节单行）：行级无事可做，**行内字符级**把注释缩到
恰好仍触发折行漂移的长度（`int first /* x…×60 */, second;` → 81 字节）——
最小复现的核心是**折行阈值**，纯行级最小化拿不到。

`--require-parse` 给判据加一道语法有效性闸（候选必须仍可解析，perses 一路的思路）；
默认关——纯文本缩减能多缩（实测会把 `int first` 并成 `intrst`，仍是同一缺陷的
最小核）。参照与"不实现语法感知缩减"的原因见 `docs/references.md`
「测试输入最小化与回归沉淀」。

## 纪律

- fuzz 发现的 bug **最小化后沉淀为 edge 语料**（clean/ 或 reject/），成为回归。
- edge 门禁进 CI（`python tests/edge/run_edge.py`）；fuzz 在 CI 里给时间预算
  （如 60-120s）跑。
- differential 依赖 Verible 二进制：先跑
  `powershell -File tests/differential/fetch_verible.ps1` 下载到
  `tests/differential/.tools/verible/`（gitignored，不入库）；harness 自动发现
  （也可用 `VERIBLE_FORMAT` 环境变量或 PATH 指定），缺失则跳过——CI 可选 job。

## fuzz 已发现的真实 bug

| Bug | 根因 | 修复 | 回归用例 |
|---|---|---|---|
| 垃圾过 lint → 静默 success=True + 丢内容 | 管线不检查 `parser._parse_truncated` | `pipeline/_stage_parse` 截断即失败 | `edge/reject/truncated_garbage.v` |
| `module name #()` 空参数表解析不了 | `ParameterList` 的 `@ParamDecl` 必需 | grammar 改可选 | `edge/clean/empty_param_list.v` |
| 畸形 ANSI 函数端口 → assert 崩溃 | `_production.py` `assert old_node is not None` | 断言改安全恢复（用户输入永不崩溃） | `edge/reject/ansi_port_missing_name.v` |
| 自引用宏 → MemoryError 崩溃 | 宏体预展开循环每次迭代翻倍（2^128），`max_iterations` 只限次数不限体积 | 直接自引用跳过（GCC 语义）+ 体长上限兜底 | `edge/reject/self_ref_macro.v` |

> 规模数据（2026-08-22）：800 轮发现 3 bug 类；5000 轮追加 1 崩溃类
> （自引用宏）+ 1 oracle 假阳性类（`timescale 指令未入排除列表，已修）；
> 修复后 2000 轮 0 崩溃，仅剩已知良性类（module 头括号规范化）。
> C 包首轮（2026-09-26，`--pack grammar/c`）：**4000 轮 0 findings**（21 iter/s）——
> 同时说明"链路已通"与"当前没有活缺陷可演示"：最小化/沉淀的端到端验证因此走
> 注入式假管线（`tests/policy/test_fuzz_shrink.py`），真实路径在 C 包的
> 注释折行漂移个案上跑过（86→81 字节，1-minimal，因缺陷未修而**拒沉淀**）。
