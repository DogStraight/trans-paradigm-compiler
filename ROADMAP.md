# ROADMAP（中长期目标 / backlog）

> 承接**中长期、非发布阻塞、backlog、v0.2 候选**类条目；短期活跃待办在
> `TODO.md`。纪律同 TODO：只列未完成项、**完成即删**（历史在 git log，决策
> 依据在机制文档），每项 ≤8 行 + 链到机制/gap 文档。容量上限由
> `tests/policy/test_planning_doc_budget.py` 守。
> P 编号沿用拆分前的原始编号（与 git 历史、交叉引用对应），不重新编号。

## 当前主线（作者 2026-10-09 定调）

> 1. **补齐 C 包框架缺口**（阶段 3 → 4 → 5，见「C 语言包」节）——当前唯一主线开发面。
> 2. **性能化改进**（0.1.4 = 高性能组件，作者既定；热点结论见 P2.3/P3.5）。
> 3. 之后**缓慢迭代**（按需修边界、补语料、打磨诊断/渲染）。
>
> **进度刻度**：到 0.1.4 的剩余刻度与退出判据状态见 `PROGRESS.md`（每轮收口更新）。
> **刻度完成后的全项审查**（作者 2026-10-21 定）：主线 1 刻度 7→9 完成后、P3/性能类改动之前，
> 做一次引擎能力面全项审查——判据 =「能力×语言矩阵 + 第二语言复用实验」，台账见
> `docs/gaps/gap-engine-abstraction-audit.md`。每多一门语言多一套特殊处理 = 一个未审查的抽象。
>
> **架构基本定型**：除非编译理论出现重大突破，不再做架构级重构——**指部件结构稳定**（子系统划分
> 与接口边界）。**插件形态与插件能力是架构中持续增长的位置**（AST 后插件开放），新增插件形态
> **不属**"架构级重构"。细节决策由维护者自决（`policy/collaboration.md`「决策权归属」），框架级才回作者。

## 工具链定位 + 语言包战略（2026-08-29 定调）

> **工具链定位（市场面）**：面向**整个语言生态**——① 既有语言上做**递进式改进**
> （插件/增量机制）；② **完整实现新语言**（c4 已验证框架，见
> `docs/language_walkthrough.md`）。"语法即资产 + 语言知识不进代码"使引擎不绑定领域。
>
> **语言包战略**：**主体语言包 = 两个**——Verilog-2005（已闭环）+ C23（`grammar/c/`），
> 是**资产范围**而非**能力边界**；其他语言（如 SV）按需以**核心 + 增量插件**支持。
>
> **c4 定位**：两个角色——"从零搭语言"起步模板 + 代码生成/多后端演示（P4.1 首个场景）。
> **"c4 被 C 包吸收"不是正确终点**（产物是 c4 VM 汇编，与 C 包目标相反）；退场判据 =
> 那两角色被别处接管，按"删除先证后删"**整包删除**。

## 用户侧 CLI 形态（中长期，触发式，无需求不动）

> 语言作用域机制（`begin_language` / `active_plugin_classes` /
> `_ensure_language_config`）解决**同进程多语言**，目前只有测试在用；CLI 全线单文件，
> 而 API 侧 `ProjectChecker.check(paths)` 已多入口——两侧不对齐。
> **触发条件**：出现真实的批处理/多语言使用场景。

- [ ] 多入口/批处理：目录递归 + 多文件（拒绝清单/退出码语义需定）
- [ ] 多语言路由：`--lang` 显式指定，或按扩展名/目录映射语言包
      （需先定：一次调用内切换语言包 vs 拒绝混语言）
- [ ] 输出聚合：多文件诊断的稳定排序 + 机器可读汇总（对齐 `--json` 现有形态）
- 附带价值：它是 P3.4（常驻 watch + 增量 check）与 LSP 形态的**最小前置**

## C 语言包（主体语言包）——核心基线 + c11/c17/c23 已交付（0.1.3）

> 设计定调（2026-08-29）：**按语法插件包形式逐步支持 C 各标准**——插件组合等效某个
> 标准的语法，而非一次性做全量（`token_ext` / `directive_handlers` / `[grammar] files`
> + `inject` + `requires` 链，零引擎新机制）。已交付面（结构/档位/已知边界）见
> `grammar/c/README.md`，边界档案见 `docs/gaps/gap-language-pack-scope.md`。
> **边界诚实**：语法层可完整等效，语义层是渐进项（先语法后语义）；预处理器是最大
> 难点，作独立阶段评估。本条只留**未完成项**：

- [ ] **阶段 5 标准等效验证**：`[plugins] enabled` 组合 → 语法接受域断言（对标各标准
      语法规范），并接真实 C 语料。**入口已就位**：`tools/c_acceptance.py`（48 条构造清单；
      当前空洞状态复现：`python tools/c_acceptance.py`，**口径注**见 gap-c-preprocessor-scope ⑭）
      + 档位参数 `resolve(...)`（判据 `test_c_standard_tiers.py`，构造数按
      `pytest --collect-only -q` 实测）。**断言面第一批已交付**（循环 #33/#35）：
      静态断言族的接受 / 拒绝 / 下档三态双向断言（`test_c_standard_conformance.py`）+
      **三处作用域**（文件 / 块 / struct·union 成员表，成员位走容器级空槽位）+ C23 分派器两分支；
      gcc oracle 照出的语法缺口**已清零**（字面量前缀族/二进制常量 #37、数字分隔符 #38、
      单参下划线拼写 #41、枚举固定底层类型 #42；清单历史见 gap「C 标准等效缺口」）。
      **剩余**：其余构造的双向断言面 + 真实 C 语料接入（退出判据 5；#43 方案 =
      `docs/gaps/gap-c-real-corpus.md`；#44 已收口 G1 说明符顺序 / G2 指针限定符，
      余 G3 未命名指针形参（#45）与 G4 typedef 强转（切片 1b，最大前置）
- [ ] ⚠ **三者顺序（作者 2026-09-28 授权自定）**：**先阶段 3**——它是切片 1b 的前置
      （符号表/作用域/声明顺序），也是"AST 之后那半段"的第一个真实入口；阶段 4 与语法面
      解耦、独立评估；阶段 5 随真实语料接入滚动做。排期：0.1.4 是**高性能组件**（作者既定），
      这三项在其后
- [ ] **注入机制：四类注入面，按需实现**（作者给的**分型**，不是实现清单；缺哪类等真需求）：
      · **① 无点位依存注入**——**有**：插件 `[grammar] files` + 语句发现（`is_statement`/FIRST 集）；
      · **② 依赖点位注入**（`targets = ["@Rule.production[N]"]`）——**有**且 fail-fast
        （c11/c23 增量全靠它）；代价 = 点位要列全，**找得到公共宿主就不必列点位**
        （`_Alignas` 改挂 `TypeQualifier`，一次注入六处生效）。**表达力边界已补足**：
        只能"并入既有元素"或"越界追加到末尾"，**插不了序列中段** ⇒ 用核心**空槽位**
        （`production = []` 的非块规则 + 宿主写 `@Slot*`）落地（见
        `grammar/grammar_rule_fields.md` §production）；
      · **③ 具体路径修改**——**只有软路径**：`inject_replace_rule` 是 production 的字符串
        子串补丁且软失败（目标缺失仅告警）；**④ 移除语法路径**——**无**。
      要做的是把 ③/④ 补成与 ② 同级的**结构化、fail-fast** 声明面（统一 `[inject]` 的
      add/replace/remove 三动作）。**触发条件**：出现真正需要"改/删既有分支"的标准演进

## C 语义层切片 1b / 语义基座（typedef 名起头的转换）

> **后续替代（2026-10-22 立项）**：**退役 `pre_scan`、改两阶段 lint**——raw 资格改符号无关
> （双读试解析），符号判定后移 analyze（E002/E003 安全网），落地后删除 lexer 预扫描机制；
> 设计/分片/判据见 `docs/decisions/0024-two-phase-lint-prescan-retirement.md`，执行项在 `TODO.md`。
>
> **已全线交付**：切片 1a（关键字起头）随 0.1.3；切片 1b = P1 符号收集 → P2a 收敛判定 → P2b-1 标记
> → P3b-M1 资格判定 → P3c 位点发现面 → M2 raw 承载 + 窄档摘诊断 → P4 理解路径（循环 #2–#9，
> `(myint)x` 闭环 + 渲染保真）。**完成项已删**（历史见 `CHANGELOG.md` + git log）；裁决全表与实现
> 边界见 **`docs/gaps/gap-c-semantic-base.md`**；残留边界项见 `TODO.md`。

## 打包：规格跟随语言包（原 ADR-0010 draft 收敛删除）

> 语言包战略的兑现侧：用户把语法配置调试稳定、需求测试完成后编译打包。现状：facets.json
> 开发者硬编码 + `_RULES_REL = "grammar/verilog"` 写死 ⇒ **无"用户标定"声明面**，c4/未来
> C 语言包打包不了。方向：打包规格跟随语言包——`grammar/<lang>/tpc.toml` 新增 `[packaging]`
> 段；build_pipeline 改为扫描语言包声明，`_RULES_REL` 硬编码消失。
> **触发条件**：非 verilog 打包需求。

- [ ] `[packaging]` 段声明（target/description/facets，facets 缺省取 `[commands]` 键）
- [ ] `bundle` 方式可选：`embedded`（语法包打进 exe，自包含单文件）/
      `external`（语法包外置，引擎原生 + 语法可换，同一二进制多语言/版本）
- [ ] build_pipeline 扫描语言包声明（`--lang` / 无参=全部），去掉 `_RULES_REL` 硬编码
- [ ] 入口生成用该语言包 rules_dir（与调试时 main.py 行为一致）
- [ ] 多语言打包验证：verilog + c + c4 各自声明、各自出 exe（embedded + external 各验证）

## P2 — 工程化收尾

### P2.3 验证吞吐优化（backlog，非发布阻塞）

> 动机：验证（fuzz/差分/edge）是"验证附着于配置驱动语言定义"的差异化能力，快速验证层是
> "模型写配置 → 自动验证闭环"成立的前提（详见 `tests/fuzz/README.md`）。现状：linter
> packrat 记忆化（管线 -92%）+ 渲染器 doc 布局记忆化（单遍 -57%）+ 回归并发化（`-n auto`：
> 300s → ~78s）；fuzz 实测 ~40 iter/s。下一热点 = parser（单遍 ~50%）；packrat **失败**
> 记忆化已回退（失败尝试也递增 `sibling_counter` ⇒ path 编号变，需先重构计数语义）。

- [ ] fuzz harness 吞吐三件套：语法表/parser 跨迭代缓存（~2.5x）/ fuzz 模式关闭管线
      内部幂等复跑（~1.8x）/ multiprocessing 多 worker（~8x）
- [ ] 随机合法程序 → 对拍 Verible：接受域从人工语料推到统计意义（GrammarFuzzer 生成器
      已由 `run_fuzz.py` 接线并进 CI；剩余 = 生成大批合法程序做 Verible 接受域统计对拍）
- [ ] 阶段级 fuzz（lexer/parser-only 不变量，比全管线再快 10-50x）
- [ ] CI 补强：differential 门禁未接入——需 verible 二进制（`nightly.yml` 已留可选 job，
      接入时用 fetch 步骤或 `VERIBLE_FORMAT`）

### P2.6 tpc-check 外部 checker 插件协议（非发布阻塞）

> 📎 详细缺口档案：`docs/gaps/gap-tpc-check-external-checker.md`。拿来主义 + 声明场景：
> 语言包 plugins/ 声明**外部 checker**（官方检查，如 `veryl check`/verible/slang），tpc 只
> **声明自己的检查场景**（官方 checker 的缺口：格式化保真/变换等价/语法资产一致性）。

- [ ] **插件声明协议**：`grammar/<lang>/plugins/checker/tpc.toml` 两段——
      `[checker.external]`（命令 + 输出解析声明，收口稳定接口：JSON 输出/稳定规则 ID）
      与 `[checker.scenarios]`（tpc 自管场景：format_fidelity / transform_equivalence /
      语法资产一致性）
- [ ] **诊断归一化**：外部 checker 输出（miette/JSON/文本）转 tpc 统一诊断模型
- [ ] **场景声明语法**：检查场景 = TOML 数据（gate 引用 run_all/差分基线），引擎只做
      通用场景执行器
- [ ] 验证路径：`grammar/veryl/plugins/checker/` 先做 veryl 本体验证，再推广 verible/slang
- 关联：P1.9（诊断模型）为其前置；调研落 `docs/references.md`（本地镜像 `E:\research\veryl` /
      `E:\research\svlint`）

### P2.8 门禁系统增强（长期；2026-09-11 登记，2026-09-12「门禁体系改进」两条并入）

> 门禁架构成熟（`global_state` 隔离 / smoke 分层 / `tests/policy` 元门禁 / 量化评测 /
> 差分 oracle），但有多处**隐式契约**会随规模（加语言包 / 检查族）复发；性质 =
> 把"记得做"门禁化。非发布阻塞，长期逐条做。

- [ ] **smoke 覆盖检测**：新增/改动功能文件未标 `@pytest.mark.smoke` 时提示，或输出
      "未进层"清单供人工判断
- [ ] **系统 1 完整性证明**（可选）：IEEE 1364-2005 附录语法产生式 → 规则 → 测试逐条
      对齐表（现 **265** 条规则——`python tools/render_coverage.py` 口径含插件规则；
      "已测未逐条对表"，完整性未证明）
- [ ] **按需门禁的定期节奏**：`tools/feature_sites.py compare` 与 `tools/check_gate_efficacy.py`
      同属"按需跑"，基线/变异会**静默过期**（实测：`feature_sites` 基线 2026-09-25 后未更新，
      重录才暴露 `formatter` 78→80、`config` 散点增长等偏差）。判据：定一个可执行节奏
      （接入 CI 或收尾轮固定跑一次）并写进 `tools/README.md`
- [ ] **分层随规模扩展**：新语言包/检查族立项时同步定义该语言自测子集；最贵层（真实
      语料全量 + 差分）留发布门禁；`timeout` 阈值随并行最坏耗时复核
- [ ] **跨文件语料基座（语料侧）**：多入口 `check(paths)` 已落地，缺的是语料本身——SERV 工程只放了
      top 文件，13 个 `serv_*` 子模块定义不在语料里，故 `W101=13` 是**真未知**（实测全部来自
      `ref_serv_top.v`）；补齐即可降（门禁"只许减"自动放行）。待补：同编译单元多文件、`default_nettype`
      跨文件泄漏
- [ ] **毒配置清单化（变异维度化）**：`tools/check_gate_efficacy.py` 现有 **108** 条真实事故变异；可扩成
      维度化清单（语言 × 执行顺序 × PYTHONHASHSEED × 缓存状态）并定期接入 CI。判据：每条变异**可复现变红**

## P3 — 增量解析（v0.2 核心，非收尾）

> P3.1（span 绑定）+ P3.6（宏体入树）已实施（机制见 `preprocessor/README.md` +
> `pipeline/README.md`）。

### P3.2 失效判定 + 增量重解析

> 设计思考落档（原 ADR-0009 draft 收敛删除）——双向映射 / 结构锚定 / 补头补尾 /
> merge 校验 + 全量回退 / 缓存选址（.code_cache 内容寻址 vs temp，key 含语法版本签名）。

- [ ] token 级 diff：新旧 token 流对比，标记变更 token（复用 lexer）
- [ ] 变更 token → 延展到语法边界（沿 `is_statement`/`is_block` 规则向外，到完整可重解析单元）
- [ ] 仅重解析受影响单元（`ParseContext` 从边界起始 token 驱动）
- [ ] 并树：替换 AST 中对应子树（类似 `merge_segments`，下沉到语句级）

### P3.4 增量 check（语义失效传播）

> 用户需求：check 也需**激活等待机制**——只扫激活区域与被涉及的链上文件（5 万行实测
> check 45s；增量是"编辑→亚秒反馈"的必经路径）。底座非从零：elaboration 的 module_index /
> connections / signal_graph 就是失效传播的图基础。① **激活** = 编辑/保存激活改动区域
> （常驻服务 + 文件监听）；② **解析层增量**复用 P3.1/P3.2；③ **语义失效传播** = 三类链
> （定义/实例化/信号，见条目），失效集 = 受影响文件 × 受影响规则（**规则声明失效键**）；
> ④ **边界诚实**：宏展开 span 映射、**漏失效 = 漏报**（判不准的改动**保守降级**为全量）、
> 小项目阈值（簿记开销反超时自适应全量）。

- [ ] 规则失效键声明：每条规则声明依赖键（模块/信号/符号），改动→键→规则映射
- [ ] 三类链传播：定义链/实例化链/信号链 → 失效文件集
- [ ] 信号图增量更新：connects 变化 → signal_graph 局部更新（不重建全图）
- [ ] 保守降级：无法精确定位的改动 → 全量该文件/该规则（防漏报）
- [ ] 小项目阈值：文件数 < N 直接全量（增量簿记开销反超）
- [ ] 部署形态：常驻服务 + watch 激活（触发式，编辑→亚秒反馈）
- 前置：P3.1 → P3.2 → 本条目；跨文件规则（W104/W105）的增量正确性需信号图增量先验证

### P3.5 Rust 热路径下沉（PyO3，远期）

> 破 Python 动态机制天花板的长期正道（Nuitka/PyPy/官方 JIT 均实测闭环，见
> `docs/references.md`）。**形态 = PyO3 热路径下沉，不是全量重写**：Python 壳保留（配置
> 驱动/插件/可模型性是差异化资产），Rust 下沉**引擎通用算法**（lexer 扫描 / 解析器骨架 /
> doc 布局）——语言知识仍在 TOML/插件层，`check_hardcode` 硬约束不破。
> 前置：P3.1 span 绑定先行（解析器接口稳定后才值得下沉）；算法层收益先吃干净
> （parser 记忆化 / P3.4 增量 check 是零语言风险的收益，顺序不能反）。

- [ ] 解析器骨架下沉：_production token 循环 + pratt 原子匹配（单遍 ~50%）
- [ ] doc 布局下沉：_best/_flat_w 热循环（~36%，已记忆化仍 Python 常数）
- [ ] lexer 扫描下沉：token 化循环
- [ ] PyO3 接口契约：Node/AST 桥接 + span 映射（依赖 P3.1）

### P3.3 已知坑：宏展开下的双向映射

- [ ] **span 是"展开后"token，不是源文本**：编辑 diff 在源文本上做、span 在展开后 token 流上
      ——需映射层；预处理器已有反向资产 `preprocessor/_bridge.py`（锚 + 原文回插），增量需
      **复用这套桥**打通"展开后 token → 源文本行"；条件编译与宏定义编辑会整段/全量失效

## P4 — 多后端输出 + LLVM IR 前端桥（v0.2 商业向候选）

### P4.1 多后端输出机制 + LLVM IR 目标插件

> 引擎级"换插件换目标"：语言包声明**多个输出插件**，引擎按目标参数选择后端、可并存输出。
> 现状：c4 仅 `asm_gen` 一个 TransformPlugin；LLVM IR 是第一个落地目标，也是"同一语言
> 多目标并存"首个验证场景。

- [ ] **多后端输出机制（引擎级）**：后端 = **同构渲染器实例**（同一个 `Renderer` 类，
      仅布局配置不同），语言配置留在插件目录，主管线渲染器只负责主 AST 原样打印。
      引擎补丁 3 处：① `Renderer.__init__` 加 `layout_dirs`（插件级布局目录后加载）；
      ② plugin_loader 识别旁路后端插件（`[transform] target`）→ 实例化同构渲染器；
      ③ 旁路插件基于**源 AST**（transform 前）产出 → 交自己的渲染器 → 独立文件输出
      （复用 mark_extra 通道）。配置复杂度 = O(插件数)，主管线零改动
- [ ] **c4 增加 LLVM IR 输出插件**：类比 `_asm.py`（@register_plugin），c4 AST → LLVM IR
      文本（define/load/store/br/icmp 等基础指令集）
- [ ] 与现有 c4 VM 汇编输出并存（同一语言多目标，验证"换插件换目标"）
- [ ] 验证：c4 小程序（if/while/函数调用）编译为 LLVM IR，`lli`/`clang` 可执行

### P4.2 对外证明能力（信任建立）

- [ ] 选一个垂直场景做端到端 demo（如 DSP 专有语言 / 硬件描述子集 → LLVM IR），配
      "配置驱动 vs 传统方案"的成本对比
- [ ] LLVM/MLIR 社区开源一个 tpc → LLVM IR 插件（技术背书路径）
- [ ] 技术博客/论文："配置驱动语言→IR"（可引用的专业形象）
- [ ] 从小而垂直的厂商切入（大厂有自研团队，小厂缺人决策快）

## 渲染器后续（原 P5 六项已全部闭环）

> P5 六项全部落地（历史见 git log / ADR-0006）。残留缺口评估见 `renderer/renderer_architecture.md`
> 「功能缺口评估」+ `grammar/verilog/plugins/formatter/README.md`「世界 B 边界」。唯一未闭环后续：

- [ ] **Layout TOML schema 校验**（`renderer/renderer_architecture.md` 缺口 5）：布局表达式
      错误（拼错原语键/类型）静默降级为 None，与 fail-fast 精神相悖——可加布局 schema 校验
      （渲染增强侧，非配置加载主路径）
- [ ] **与外部格式化器的排版对拍**：token 序列对拍已由 C 包保真判据 7 覆盖（内容级、
      语言无关），"与 clang-format/verible 的**排版**对拍"仍未做（属验证面，非缺陷）

## SystemVerilog 语言包（远期 backlog）

> Verilog-2005 全量（P1.8 批次 1-6 + 审查修复）后的自然延伸；当前决策：**缓行**——先
> 稳定/玩熟 verilog 全量。规模估算：语法层全量对标 sv-parser（IEEE 1800-2017 Annex A）
> ≈ 净增 800-900 条规则、8-12 个月；SV 核心子集（综合常用面）3-4 个月；SVA/class/
> constraint 是最大三块。**定位（2026-08-29 修正）**：SV 不在**个人**主体需求内，但
> **工作需求下会做**，形态为**核心 + 语法插件**逐步全量（与 C 标准插件族同构）。
> 触发条件：个人侧 = verilog 验证闭环稳定、P1.8 批次 7 候选缺口清完后立项；工作侧 =
> 出现 SV 需求时按插件族启动核心，随需叠加。

- [ ] 阶段 A：SV 核心（= 核心包基线）——2-state/logic、struct/enum/typedef、always_comb/
      ff/latch、接口+modport、package+import、generate 增强、`.name`/`.*` 端口、尺寸字面量
- [ ] 阶段 B（增量插件）：OOP/约束——class、继承、constraint、rand
- [ ] 阶段 C（增量插件）：最长尾——SVA 断言、covergroup、checker、randsequence
      （+ pratt 运算符族/引擎扩展）
- [ ] 阶段 D：收尾——SV 预处理器扩展（宏带参/双反引号）、sv-parser 差分清零、lint 精度、
      渲染打磨

## 语言知识渗透复审（L1，长期方向，未见排期）

> 判据三条（全表见 `docs/gaps/gap-language-penetration.md`）：① **最小语言包探针**
> （主判据，行为面，`tools/min_pack_probe.py` + 基线；已做）；② **声明面缺失探针**
> （临时删一段语言包声明跑测试，仍绿处 = 引擎替声明做事）；③ **弱信号面**
> （`tools/lang_penetration.py`）。三条都只覆盖**被测路径** ⇒ 结论只能是"已知渗透面
> 收敛"。范围：**重点 analyzer / preprocessor / linter**。**剩余面 = 精化基座之外的
> 渗透复审**（判据 ②/③，按需在改动时顺带做）。⚠ 新增语言包作暴露法只在隔离跑
> （每语言一进程）下可用——多语言同进程已有真实串味史，不作日常手段。
> **引擎 vs 插件能力边界的设计原则**（三分法 / 两失效信号 / 普适原语清单）见
> `core/component_protocol.md`。
