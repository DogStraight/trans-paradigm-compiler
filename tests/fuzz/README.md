# Fuzz / 差分 / 边缘构造验证（tests/fuzz, tests/edge, tests/differential）

> 动机（known_limitations 原话）："Validation is sample-driven, not exhaustive…
> no fuzzing, property-based, or differential testing yet"——本目录补齐这三块。
> 语法是数据 → fuzzer 直接从 grammar TOML 驱动，无需手写生成器。

## 目录

| 目录 | 内容 | 运行 |
|---|---|---|
| `tests/fuzz/` | 语法驱动生成 + 变异 fuzzing，断言不变量 | `python tests/fuzz/run_fuzz.py --iters 800` |
| `tests/edge/` | 边缘构造门禁（clean 必须成功 / reject 必须失败） | `python tests/edge/run_edge.py` |
| `tests/differential/` | 与 verible-verilog-format 对拍（可选依赖） | `python tests/differential/run_differential.py` |

## 不变量（fuzz oracle）

1. **不崩溃**：任何输入不得抛异常（软失败可，崩溃不行）。
2. **token 保序**：格式化前后非 trivia token 序列必须一致（可改排版，不可改
   内容）。**仅对语法驱动生成的合法程序（gen）断言**——mutation 产物多为
   畸形，容错解析路径（补分号/module 头括号规范化等）会合法地改变 token
   序列，该不变量在那里不成立（见"已知的 oracle 判定"）。
3. **幂等**：`format(format(x)) == format(x)`。
4. 成功 → 输出可再解析（管线内 round-trip）。

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

## fuzz 已发现的真实 bug（2026-08-22，均已修复并沉淀为 edge 回归）

| Bug | 根因 | 修复 | 回归用例 |
|---|---|---|---|
| 垃圾过 lint → 静默 success=True + 丢内容 | 管线不检查 `parser._parse_truncated` | `pipeline/_stage_parse` 截断即失败 | `edge/reject/truncated_garbage.v` |
| `module name #()` 空参数表解析不了 | `ParameterList` 的 `@ParamDecl` 必需 | grammar 改可选 | `edge/clean/empty_param_list.v` |
| 畸形 ANSI 函数端口 → assert 崩溃 | `_production.py` `assert old_node is not None` | 断言改安全恢复（用户输入永不崩溃） | `edge/reject/ansi_port_missing_name.v` |
| 自引用宏 → MemoryError 崩溃 | 宏体预展开循环每次迭代翻倍（2^128），`max_iterations` 只限次数不限体积 | 直接自引用跳过（GCC 语义）+ 体长上限兜底 | `edge/reject/self_ref_macro.v` |

> 规模数据（2026-08-22）：800 轮发现 3 bug 类；5000 轮追加 1 崩溃类
> （自引用宏）+ 1 oracle 假阳性类（`timescale 指令未入排除列表，已修）；
> 修复后 2000 轮 0 崩溃，仅剩已知良性类（module 头括号规范化）。

## 纪律

- fuzz 发现的 bug **最小化后沉淀为 edge 语料**（clean/ 或 reject/），成为回归。
- edge 门禁进 CI（`python tests/edge/run_edge.py`）；fuzz 在 CI 里给时间预算
  （如 60-120s）跑。
- differential 依赖 Verible 二进制：先跑
  `powershell -File tests/differential/fetch_verible.ps1` 下载到
  `tests/differential/.tools/verible/`（gitignored，不入库）；harness 自动发现
  （也可用 `VERIBLE_FORMAT` 环境变量或 PATH 指定），缺失则跳过——CI 可选 job。

## 迭代指南

fuzz 报发现 → 打开 `tests/fuzz/findings/*.v` → 最小化 → 判定真 bug /
oracle 假阳性 → 真 bug 修 → 沉淀 edge 回归 → 重跑。
