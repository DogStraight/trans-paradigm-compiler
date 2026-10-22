# Gap — 预处理器宏展开时序（宏定义前/`#undef`/include 内顺序；T1）

- 状态：**主体已实施（#51，2026-10-23）**：真实语料 **7/7 `parse_ok=True`、syntax=0**；
  余 = 误报基线门禁落地（判据 5，下一轮）+ zutil `TAG001×2`（include-guard 跨 include
  可见性边界，登记见文末）
- 关联：`TODO.md` 1.3（T1）、`ROADMAP.md`「剩余三任务路线图」、`gap-c-real-corpus.md`
  （G4 收口后唯一余量 = 本档）、`gap-c-preprocessor-scope.md`（预处理器范围基线；本档只记
  "时序/可见性"子缺口）
- 参照：C99 §6.10.2（宏作用域：`#define` 起生效、`#undef` 后失效）、§6.10.3（宏替换/
  重扫描）、`preprocessor/macro_timeline.py`（已有事件表，只服务 MAC001）

## 缺口是什么

展开器 `preprocessor/_expand.py::expand_tokens`（`preprocessor/_expand.py:859`）在 clean
文本上**逐行**展开，但宏表 = scan_directives 汇总的**全文件最终表**（host + 所有 include
的最终状态）。C 的可见性是**顺序的**：宏自 `#define` 行起生效、`#undef` 后失效、`#include`
在包含点展开且**头内定义按头内顺序**。两个可复现形态（check 路径 = `ProjectChecker`，
临时目录构造，判据即下节）：

1. **本文件定义之前**：`int F(int);` 之后才 `#define F(a,b) ((a)+(b))` —— 原型被误展开；
2. **include 内容内部**：头文件先原型、后 `#define`（zlib.h 的 `gzgetc` 形态：原型在
   `zlib.h:1613`、宏在 `:1964`）—— 头内原型被头内**后置**宏展开。

实测（本轮探针）：形态 1/2 的最小复现均 `parse_ok=False`、syntax 3 条
（`phase-statement`，诊断带 `macro` 归因）；真实语料 5 个 zlib 文件
（zutil/crc32/adler32/compress/uncompr）`parse_ok=False`，展开产物已是坏文本
（如 `zutil.c` 展开行 1833：`extern int  ((gzFile file)->have ? …`）。cJSON/gzread
不含该形态，已 `parse_ok=True`（G4 #49 后）。

## 机制现状（为什么现有事件表不够）

- `scan_directives` 顺序扫描指令；`include` handler 递归 scan 子文件后，把**子文件最终
  宏表**在 include 行处并入 host（事件快照），`inc_clean`（子文件去指令文本）直接拼入
  host clean —— **头内定义的位置坐标丢失**（`preprocessor/primitives/include.py:150-205`）。
- `preprocessor/macro_timeline.py`：已有 `{line, name, params}` 事件表与 `params_at`，
  但**只服务 MAC001 调用点形参检查**（`preprocessor/_expand.py:1671-1705`），事件不含
  宏体，展开器不消费。
- `expand_tokens`：`_MacroExpandCtx(macro_defs=最终表, func_macros=最终表, …)`；
  行循环 `for line_no, line in enumerate(lines, 1)`（`:958`），`_collect_macro_matches`
  用**全名正则** + 最终表取宏体（`:1399`）——没有"该行可见集"。
- 文档自述：`macro_timeline.py` 头注明确"展开器对**全文件用最终宏表**（历史近似）"。

## 方案（荐否并列）

- **A（推荐，分两片）**：把时序落到展开层，不重写预处理器契约。
  - **A1 host 时序**：`expand_tokens` 接受**带宏体**的定义/取消事件（扩展现有
    `_macro_events`：`{line,name,params,body}`）；逐行维护 active 表（该行可见宏），
    `_collect_macro_matches` 只对 active 名匹配、取 active 体；`#undef` 从 active 移除。
  - **A2 include 内时序**：`include` handler 在包含点用"host 当时 active 表 + 子文件
    自身事件"递归**预展开**子文件 clean，输出已展开文本并标记"已展开"（host 展开跳过
    该区间）；host 表在 include 后更新为子文件最终表（保持现状 include 语义）。
- **B（否）**：只做 A1 —— 修不了真实语料（头内定义前），不解决唯一承重形态。
- **C（否/备）**：全流式预处理器（scan 时同步展开）——最正统，但改动
  `宏区间/行映射/渲染 splice/恢复锚` 全部契约，超本轮预算；A 已覆盖实测的顺序语义面。
- **D（否）**：语料子集/豁免 —— 5/7 真实文件都含该形态，不诚实；且判据 5 需要完整语料。

## 实施记录（#51，2026-10-23）

**A1 事件时间线**：`_macro_events` 事件扩为
`{line, name, params, op: define|undef, body}`（define/undef handler 产出）；
`expand_tokens(events=, clean_to_raw=, base_macros=, base_funcs=)` 逐行取
"`event.line < 当前原始行` 的最后状态"重建可见宏集（`#undef` 失效、重定义换体），
宏名正则 = 最终表 ∪ 事件名（`#undef` 后名字仍需匹配历史段）。`events=None` 保留
旧调用面（测试/直接调用）。

**A2 include 预展开**：include handler 在包含点用「扫描期 active 表 + 子文件自身
事件」调 `expand_tokens` 预展开子内容并拼入 clean；宿主展开器按
`clean_to_raw[i] is None`（include 拼接行）跳过，避免二次展开。`parse_raw` 模式
经 `preexpand_includes=False` 关闭。子文件事件用子文件行映射（不并入宿主坐标）。

**连带修复（真实语料暴露，均缺一不可）**：
1. 语句前**同行**注释（宏体尾注释被铺进流）无候选 ⇒ 顶层/块语句截断：
   `parser/block_parser.py::_skip_leading_inline_comments` 记 line 锚并跳过；
2. 函数指针 typedef 名未注册（`typedef void *(*alloc_func)(void);` 的括号声明符路径
   `direct.head.inner.direct.head`）⇒ `(alloc_func)0` 不强转：`[Rule.parser] register`
   的 `name_paths` 补括号声明符一层/两层（Declaration/ParamDecl）；
3. 三元 `?:` 前夹注释（宏体尾注释）⇒ linter pratt 失配误报：
   `linter/checkers/expression.py` 对含注释的表达式区间用**滤注释视图**解析并把
   消费数回映射（引擎解析器本就有注释锚，仅 linter 补）。

**验证**：新增 `tests/engine/preprocessor/test_expand_timeline.py` 6 例（定义前/
undef/重定义/include 内顺序/include 后可见/不二次展开）；真实语料 7/7
`parse_ok=True` syntax=0（zutil 余 `TAG001×2` 见下）；C/e2e/policy 全绿；A/B 0/144；
lint accuracy 33/33 fp0；render 124/124；pyright 0；变异新增 2 条（关时间线/关预展开
均实测变红）。

**残余（→ 判据 5 / 下一轮）**：
- zutil.c `TAG001×2`（`z_stream_s`/`gz_header_s` 二次带体定义）——子文件扫描不继承
  宿主/兄弟 include 的宏（include guard 跨 include 不可见）⇒ 同一头被重复展开；属
  include 宏环境边界，登记待门禁轮处理（基线或修 include 环境继承）。
- 误报基线门禁：`tests/e2e/eval_diag_baseline.py` 现只覆盖 verilog；C 需基线文件 +
  policy 入口（判据 5 收口动作）。

## 判据草案（T1 实现轮）

1. **最小复现 2 条**：上节形态 1/2 的 check `parse_ok=True` 且展开文本无错位
   （`expand_tokens` 产物与源 token 序列一致，宏调用处为宏体 token）；
2. **真实语料**：7/7 文件 `parse_ok=True`、syntax=0（cJSON/gzread 不回退）；随后
   `评测基线 + 门禁`（判据 5）才能上；
3. **回归**：`tests/engine/preprocessor` 全绿；行映射/宏区间/渲染 splice/幂等
   （`tests/e2e` 相关）不回归；verilog A/B **0/144**；全量 `pytest tests`（冻结树）；
4. **变异**：去掉时序过滤（用最终表）⇒ 判据 1 红；去掉 include 预展开 ⇒ 判据 1/2 红。

## 预算与止损

- 分片：A1（1 轮）→ A2（1 轮，含 `expand_tokens` 入参/已展开区间标记/行映射）。
- **止损**（预声明）：A2 若在 1 轮内无法保持 **行映射 + 宏区间 + 渲染保真/幂等 +
  verilog A/B 0/144**，则停 A2、登记"include 内定义时序"为触发式边界，语料门禁按
  2/7 + 明确豁免表落地（结论报 `partial`，不硬凑 7/7）。

## 不做 / 未做

- 不引入第二套宏展开算法（hideset 重扫描仍唯一算法；A 只改"宏表可见性"输入）。
- 不在本轮实现（调查轮：只落位置/方案/判据）；C 侧 `#undef` 文件级时间线已由
  `macro_timeline` 证明语义可表达，不重复。
