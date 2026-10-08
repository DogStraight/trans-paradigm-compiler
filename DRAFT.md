# DRAFT（短期草稿：预期外 / 未定判观察）

> **定位**：不进 `TODO.md`（有判据可执行）、`ROADMAP.md`（中长期）、`docs/gaps/`
> （现状边界）与 `docs/decisions/`（生效决策）的**暂存区**——现象已实测，但
> **出口未定**（要修/要接受/要立项）或**影响面未知**。
> **每条必写四段**：现象（含实测证据）+ 待判点 + 出口 + 立条日期。
>
> **防膨胀纪律**（防这片草稿变成第二个 TODO）：
> · 上限 **8 条 / 70 行**（`tests/policy/test_planning_doc_budget.py` 守）；
> · 每条必须在**下一次相关改动或收尾轮**落定出口：修 → `TODO.md` + 测试 + `CHANGELOG.md`；
>   接受 → `docs/gaps/`；立项 → `ROADMAP.md`；判废 → 直接删；
> · **清空即删本文件**（历史在 git log）；不登记进 `MODEL_INDEX`（草稿不入对齐体系）。

## 条目

- [ ] **D-1 `tpc check` 精化产物丢 token 的「用户可见影响」未证明**（2026-10-08 立）
      · 现象：接线缺失时，值表达式内带行注释会让产物文本丢 token（`param_default` =
      `'4 // note + 2'`，正确为 `'4 + 2 // note'`）；接线已全仓对齐（生产两处 + 5 处 harness，
      判据三条）。
      · 待判点：**修复前的丢 token 是否曾改变用户可见诊断**？六个样本上诊断面无差异
      （0/0、均 exit 0），现象是**静默的产物文本退化**（下游对不可判文本按保守处理）。
      · 出口：消费方分析或更大样本轮给出"有/无可见差异"结论——有差异则立 `TODO.md` 条目，
      无差异则本条删除、现状归 `docs/gaps/gap-language-pack-scope.md`。

- [ ] **D-2 `c99` 核心基线要不要再切一层 `c89` 基线**（2026-10-08 立）
      · 现象：`//` 注释、`long long`、`_Bool`、`for` 声明式、指示符初始化、复合字面量、
      变参 `...` **都是 C99 相对 C89 的新增**，现已全部进核心基线 ⇒ "C89 等效"不可表达。
      · 来源：0.1.3 阶段 0 定界时记为"首个待决项"（那段一次性计划已随交付收口删除，
      **本条是它现在的唯一落点**——不落这里就丢了）。
      · 待判点：这是**接受的范围声明**（核心基线 = C99 语法面）还是**要补的档位**？
      · 出口：作者一句话判——要做 → `ROADMAP.md` 立"c89 基线档"；不做 → 落
      `docs/gaps/gap-language-pack-scope.md`「C 语言包：接受域现状」的范围声明，本条删除。

- [ ] **D-3 yaml `yaml_neg` 声明的可达性**（2026-10-08 立；来源 = 已裁的
      `gap-language-pack-scope.md` 词法面「写包者须知」第 2 条"记载待处理"）
      · 现象：lexer 只在数字字符上进入数字扫描，故 yaml 的 `-5` 一直是
      `symbol.base.minus` + `5`，`yaml_neg` **从未生效**（门禁
      `TestLeadDotConfig::test_starts_at_declared_non_digit_is_gated` 记了这个反例）。
      · 待判点：这是**死声明**（应删配置，命中"删除先证后删"A1）还是要**修的 lexer 缺口**
      （yaml 负数字面量该成单 token）？
      · 出口：判死声明 → 删 `yaml_neg` 并跑 yaml 全绿；判缺口 → `TODO.md` 立条目 + 正负样本判据。

- [ ] **D-4 `tools/feature_sites.py --compare` 的基线自 2026-09-25 起未更新 ⇒ 散点增长无人守**
      （2026-10-08 立）
      · 现象：本轮为改 `kept.json` 引用而 `--save` 重录时，吸收的**存量漂移**说明基线已过期
      ——`formatter` total 78→80、`config scatter` 26→29（`style_check` 2→7、
      `macro_hygiene` 4→6）；该工具的 `--compare`（增长即 exit 1）**按需跑、不在 CI**，
      故漂移静默累积。
      · 待判点：这是按需工具的固有代价（接受，写进 `tools/README.md`），还是要**定期接入
      CI 节奏**（与 `ROADMAP.md` P2.8「毒配置清单化 + 定期接入 CI」同族）？
      · 出口：接受 → 现状归 `docs/gaps/gap-feature-scatter.md`；要守 → `ROADMAP.md` P2.8 加一条。
