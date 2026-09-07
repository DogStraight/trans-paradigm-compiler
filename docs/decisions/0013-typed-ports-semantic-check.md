# ADR-0013: typed_ports 增强语法语义检查（T3，首个自场景自定义规则）

- Status: accepted（2026-09-07 立项实现；机制落 typed_ports 组件后本决议收敛删除）
- Date: 2026-09-07

## 背景

`type`/`role`/`impl`（typed_ports 插件）是 tpc 注入 Verilog 的增强语法，
主流工具（Verilator/svlint/Verible/slang/Spyglass）**完全不识别**——对它们
这是语法错误或噪声，因此这套语法的语义良构性只有 tpc 自己能保证，天然无
对标 → 满足"只用于我场景"的差异化自场景。

现状（2026-09-05 代码观察）：typed_ports 6 个 handler grep 诊断/错误/检查
**0 命中**——全部是防御性静默，坏输入不报错，产出错误展开：

| 坏输入 | 现在行为 | 后果 |
|---|---|---|
| `impl` 引用不存在的 type | `type_map.get(iface_name)` 落空 → auto_connect 原样返回 | 增强语法未展开/残留，无诊断 |
| `spi.<不存在的 role>` | `_resolved_ports` 找不到 role → 端口空 | 包装模块无端口，静默 |
| 显式连接 `.typo_port(x)` | build_wrapper 把不在定义端口集的 impl 端口 **append 进 wrapper** | typo 被当成新端口，产出错误模块 |
| `invert <不存在的 role>` | （_invert_map 未查） | 静默 |

## 目标函数

语义检查的意义 = **给出足够的结构完整度，让解释器/编译器能按语法理解这段
代码**。typed_ports 不是"端口复制宏"，而是一层**类型化接口声明**：`type` =
接口类型、`role` = 方向视角、`impl` = 类型化连接。检查保证编译器读增强语法
时无歧义、可还原成确定的 Verilog 结构——坏输入（引用悬空/类型错配/方向
冲突/表述残缺）在展开前被拦成诊断，而非静默产出错误的展开。

## 决策

### 1. 检查维度三族（检查点 11 条）

- **A 表述完整（语法自洽可还原）**：type/role/invert 引用存在、role 端口
  归属、无重复无环——表述残缺则编译器无法还原结构。检查点：type 引用存在 /
  role 存在 / 显式端口名归属（∈ 定义端口集）/ type 定义良构（role 内端口名
  不重复、invert 无环）/ invert 合法性（role 存在 + 非自反冲突）。
- **B 连接正确（类型化 + 方向）**：跨类型端口不能互连（spi 端口不能连
  sci）、显式连接端口名 ∈ 定义端口集、连接方向与定义方向一致。检查点：类型
  匹配 / 方向一致（驱动模块不能驱动有驱动的端口）/ 实例角色对齐（连接两端
  互为 master/slave，invert 语义在此落地）。
- **C 单驱动（一个端口一种驱动方式）**：端口映射落点是一个模块，一个物理
  端口只有一个驱动来源；需要不同行为 = **新语法**描述，不由既有端口承担
  多重语义。检查点：单驱动（auto_connect 与显式连接不重复驱动同一端口）/
  驱动方式互斥（一个物理信号不被两个 role/impl 同时驱动）。

时序：全部检查在 analyze pass（transform 前）执行，坏输入不进入展开。

### 2. 架构：诊断放 typed_ports 组件内（不建 checks/ 族）

判据：这批检查是**展开正确性必需（编译错误性质）**，不是可配置 lint——
恒开、error 级、不可关（checks 族"默认开关是数据决策/用户可关"的语义与它
冲突，关了 = 允许静默产出错误模块）。检查知识（type/role/invert/连接方向）
与组件展开同源，放组件内复用现有原语链（type_map/role 端口集/invert 映射）
零重建防双实现漂移；组件（语法+语义验收+展开）自洽可装卸。

机制事实（2026-09-07 确认）：analyzer primitive 手里有 `context.report`；
组件内诊断照常进统一报告管道（文本/HTML，report_html.py）；suppress 是输出
层过滤、对诊断来源不敏感（`tpc-check off/disable-line` 同样覆盖组件内诊断）；
`tpc check` semantic 阶段收 analyzer 插件诊断。

- code 前缀：typed_ports 专属 `TPxxx`（组件语义契约，不混入通用族）。
- 可选/风格类（若未来出现，默认关/用户可配）才走 checks 族——正确性类全在
  组件内，此切分是判据的自然延伸。

### 3. 阻断语义：TP error → 不走展开（硬门禁非软报告）

展开路径已暗含使用增强 tp——若 TP 诊断为 error，**直接产出错误，不走后续
展开**（transform 阻断）。不是"check 验收 / format 照展开"的软报告。

## 权衡

- 代价：组件内检查是 typed_ports 专属逻辑（不通用化）；TP error 阻断展开需
  在 analyze→transform 之间加"诊断是否含 error"的判断门。
- 换取：展开前拦截坏输入（编译级语义保证——类比 C++ 编译器检查模板实例化）；
  增强语法自身的验收（正确性契约 = typed_ports 该自带的验收基线）。
- 被拒绝备选：独立 checks/ 族插件（check_registry 统一）——检查是组件语义
  契约非通用检查族；checks 族会错误暗示"可选规则 + 用户可关"，且需从符号表
  重建 typed_ports 语义 → 双实现漂移。
- 借鉴落位：C++ 强类型连接（跨类型互连是编译错误）→ B；role 即方向视图
  （const 类比，master/slave 同组信号不同视角）→ typed_ports role 语义；
  单一所有权/唯一驱动 → C；SV interface/modport（type≈interface、role≈
  modport 同构）方向匹配检查作对拍参照。

## 验证

- 11 检查点各 pos/neg case（坏输入被拦、好输入零误报）。
- TP error 阻断展开测试（analyze 报 error → transform 不产出错误模块）。
- 新码进 eval_check_accuracy focus（pos/neg case，recall + FP 量化）。
- 全量 pytest 回归绿 + policy 门禁（check_doc_refs / check_hardcode）零命中。

> Impl: grammar/verilog/plugins/typed_ports/（analyzer primitives/handler，待实现）
> Test: tests/engine/analyzer/（typed_ports 语义检查，待实现）
