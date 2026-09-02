# ADR-0010: C 语言包前置研判（注入 vs 替换 + 用户标定打包入口）

- Status: draft（未立项；C 语言包立项/多语言分发需求出现时升 accepted）
- Date: 2026-08-29（研判）；2026-09-02（自 docs/references.md 迁入）
- Supersedes: references.md 同章节（内容迁移，非推翻）

## 背景

语言包战略收敛为 verilog2005 + C23 后，两个前置机制缺口暴露：①C 语言包
按"标准插件族"设计（c11/c17/c23 增量插件叠加等效标准），但增量注入机制
只有"增加"路径成熟，"修改"路径是原始补丁；②多语言分发（用户打包自己
的语言包，forkable 主张的兑现）没有"用户标定"的声明面。

## 设计输入

### 一、注入 vs 替换机制研判

- **触发**：C 语言包按"标准插件族"设计（ROADMAP）——c11/c17/c23 增量插件
  叠加等效标准。规划时发现 tpc 增量注入机制**只有"增加"路径成熟，
  "修改"路径是原始补丁**，标准演进中的"改"（如 C23 对 `int f()` 语义变化、
  K&R 定义废弃倾向）表达不了。
- **现状盘点**：
  - ✅ **增加路径（inject_productions）成熟**：结构化树层操作（choice 候选
    插入 + 全树 call 传播替换），幂等（祖先链判据防重复注入累积）、
    fail-fast（ADR-0003：目标缺失/解析失败直接报错）。
  - ⚠️ **修改路径（inject_replace_rule）是原始补丁**：`prod.replace(old, new)`
    **字符串子串替换**，非树层结构化；**仅能改 production**（不能改
    layout/analyzer/scope 等规则其他字段）；规则缺失只警告跳过（软，与
    ADR-0003 相悖）；inject/replace 是两个分离机制，插件声明里没有统一的
    "我在以什么方式改目标"声明面。
- **设计方向（未立项，仅研判）**：注入点统一声明"注入 or 改变"——
  `[inject]` 段显式声明操作类型（如 `mode = "add" | "replace" | "remove"`），
  replace 升级为**树层结构化**（feature 树精确寻址替换/删除，非字符串
  子串），并统一 fail-fast。触发条件：C 标准插件族立项（届时"改"需求真实
  出现）或 verilog 插件出现同类需求时，从 ROADMAP 移回 TODO 立项。

### 二、用户标定打包入口研判

- **触发**：语言包战略收敛为 verilog2005 + C23 后，"用户分发自己的语言包"
  （forkable 主张的兑现）成为自然延伸——用户把语法配置调试稳定、需求
  测试完成后编译打包。盘点发现现有打包管线**没有"用户标定"的声明面**。
- **现状盘点（packaging/）**：
  - `facets.json`：**开发者硬编码**的四个预置切面（tpc-fmt/tpc-lint/
    tpc-check/tpc），切面 = 命令名集合（main.py `_register_subparsers(sub,
    allow)` 裁剪）。
  - `build_pipeline.py`：读 facets.json → 生成入口脚本（entries/）→ Nuitka
    onefile（PE 署名 + SHA256）——**`_RULES_REL = "grammar/verilog"`
    硬编码**，c4 打包不了、未来 C 语言包更不行。
  - 结论：**Nuitka 编译是显式的，但"用户如何声明打包"这个需求侧面完全
    没体现**。
- **设计方向（未立项）**：打包规格跟随语言包——`grammar/<lang>/tpc.toml`
  新增 `[packaging]` 段（target/description/facets），facets 缺省取该语言包
  `[commands]` 段已有的键（零重复）；build_pipeline 改为**扫描语言包声明**
  （`python packaging/build_pipeline.py` 无参 = 全部，`--lang <lang>` =
  单个），`_RULES_REL` 硬编码消失，入口生成用该语言包 rules_dir（与调试
  时 main.py 行为一致）。与插件聚类/渲染插件同哲学：一切可声明、可组合、
  用户标定。
- **打包方式可选（2026-08-29 补充）**：语法包与二进制的结合方式由用户
  声明，不止"打进 exe"一种：
  - `bundle = "embedded"`——语法包数据打进 exe（现状 `--include-data-dir`，
    单文件分发，自包含）。
  - `bundle = "external"`——语法包外置（exe 运行时按路径加载语法目录），
    引擎原生性能 + 语法可换——同一二进制服务多个语言包/版本，分发只发
    语法包数据；"调试期解释器热改 → 使用期二进制 + 外置语法"双态连贯。
  - 两种形态语法都是**数据**（不是编译进代码），调试期热改能力不变；
    差异只在"语法随包携带 vs 外部加载"。用户可能有"语法打进二进制"的
    自包含分发需求（embedded），也可能有"引擎固定、语法可换"的多语言
    分发需求（external）——由 `[packaging] bundle` 标定。
- **优先级**：低于 C 语言包——当前仅 verilog 一个语言包要打包，硬编码
  还能撑；触发条件 = C 核心基线立项（多语言共存）或出现"非 verilog
  打包"需求。

## 权衡

- 两主题都是"未立项研判"——不实现，只记录设计方向与触发条件，供 C
  语言包立项时直接取用（避免重复调研）。
- 被拒绝的备选：立即实现（无触发需求，违背数据决策）；硬编码扩展
  （facets.json 加 c4 条目——治标，不解决"用户声明"声明面）。

## 验证

- draft：无实现验证。ROADMAP C 语言包条目 / 用户标定打包条目立项时
  以本文为设计起点。

> Impl: 待实现（C 语言包立项 / 多语言分发需求出现后）
> Test: 待实现
