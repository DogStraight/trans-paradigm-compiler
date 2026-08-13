# TODO

> 排序原则（2026-08-11 重排，由"最大缺口"评估导出）：
> - **主线 = 第二语言（P0）**：验证"语言无关 / forkable"主张是否成立，是最大缺口；
>   同时带上**开发前置类工程化**（异常层级、调试基础设施）作为支撑。
> - **工程化拆两类**：开发前置类 → P0；发布收尾类（CI/安装/文档/覆盖率门禁）→ P2，不阻碍功能推进。
> - **零测试模块先补测试再堆功能**（预处理器 / formatter），避免在无测试地基上叠加。

## P0 — 第二语言验证（主线，最大缺口）

### P0.1 前置清理与支撑（工程化·开发前置）

> 现状：`pyproject.toml`（build-system/project/scripts/optional-deps/pytest/coverage）与 LICENSE 已落地；
> 2026-07-25 质量评估遗留 P0/P1（异常层级、覆盖率门禁）。

- [x] **异常层级统一**：统一异常体系 + 清理 except 吞噬 + TOML 模式验证（2026-07-25 P0 遗留）
      ——开发新语言前清理，避免新代码踩坑
      - core/errors.py：TransParadigmError 基类 + ConfigError/GrammarError/LexError/
        ParseError/TransformError/LintInternalError 子类；ParseError 迁移继承，core.define
        re-export 保持兼容
      - config 加载路径（define._load_tpc_meta / config_registry.load_all）→ ConfigError
      - 语法验证（rule_selector 产生式片段 / define peek / lookahead 入口规则）→ GrammarError；
        linter 配置缺失 → ConfigError
      - 清理 component/plugin loader 裸 except Exception: pass → OSError 收紧
- [x] **调试基础设施**（parser + linter 共用，当前最难调试的两个模块，第二语言开发会大量依赖）：
      a) 日志分级开关（LOG_TRACE/DEBUG/INFO/WARN/ERROR，`_log_level` 阈值替代空 lambda 替换，
         修复 `debug_log_file=None` 时 WARN 被吞——parser_core.py `_log_state`/`_log_level`）；
      b) parser 停点/trace（`set_trace(rule/token_pos)` + `_maybe_trace`，`try_rule_productions`
         入口按规则名/位置过滤，输出 token_pointer/当前 token/路径——parser_core.py + _production.py；
         原 `_failure_attempts` 已升级为失败现场 `_fail_sites`，见 failure-report）；
      c) discovery 节点树 token 区间 dump（`Discovery.dump_nodes`：rule + [start,end) →
         1-based/0-based 行号——linter/discovery.py）；
      d) 行号对账工具（`reconcile_line_numbers` / `reconcile_mismatches`——core/debug_report.py）

### P0.2 Tiny C 演示 DSL（第二语言本体）

> 依据 roadmap：语言范畴参照 c4（最小完备内核）+ chibicc（特性增量）；难度中等偏高（工作量型）。

- [ ] **范畴裁剪**：定三件事——①c4 内核 vs 扩展 ②任务拆分顺序（先哪层）③核心渗透预检
      （先跑最小 lexer 验证）
- [ ] **分层实现**：lexer → parser → analyzer → transform → renderer 逐层跑通（参照 chibicc 特性增量）
- [ ] **核心无渗透验收**：全程盯"分水岭"，任何 Verilog 知识进入 core 即暴露并回改
      （picorv32 修复记录证明核心改动均由 Verilog 缺口驱动，语言无关性从未被系统验证过）
- [ ] **模型可消费性演示 + walkthrough**：产出"从零搭语言"完整示例（原"自定义 DSL 完整示例"），
      兼外部贡献者上手参考——展示"语言知识全外部化"能力，降低拿本项目当骨架/改造的入门门槛
      （当前文档全围绕 Verilog，缺"从零搭语言"的 walkthrough）

### P0.3 渗透清理（第二语言暴露的残留渗透一并处理）

- [ ] **boundary.py 语言渗透消除**：keyword.*→ScopeKind 映射外部化到配置（遵守"不编码语言知识"铁律）
- [ ] **其他暴露点清理**：第二语言验收中发现的 core/linter/transform 残留 Verilog 知识，记录并清理

## P1 — Verilog 实例完善（插件增强）

### P1.1 先补零测试的债

> 现状：预处理器与 formatter 均零单元测试（逻辑验证靠人工）。

- [ ] **预处理器单元测试**：指令原语/宏展开/ifdef 分支/逆向恢复（后续按部件分文件补充）
- [ ] **formatter 单元测试**：边界扫描器/分组/品类引擎/passes（后续按部件分文件补充）

### P1.2 预处理器增强

> 现状：已有 define/ifdef/include/undef primitives + `_expand.py`/`_reverse.py`；
> 已修复嵌套 ifdef inactive 祖先、续行拼接、include 配置化；
> 行首未知指令当前被 scan_directives 整体删除（跨子系统容错边界）。

- [ ] **管线内宏 token 决议**：行内宏调用在预处理器阶段展开/决议，管线内不再残留宏 token
      （linter P0 保险措施的前提；当前 e12 靠行内宏调用做 undefined-macro 可达性验证）
- [ ] **未知/错误指令容错**：行首未知指令从"整体删除"改为可配置策略 + 诊断报告（保留容错）
- [ ] **带参宏支持**（如 `` `define NAME(a,b) ... ``）：评估参数展开（当前仅文本替换）

### P1.3 格式化插件完善

> 现状：品类系统框架完成（boundary/engine/grouping/passes）；
> `formatter/tpc.toml` 品类配置仍为注释模板。

- [ ] **品类配置落地**：tpc.toml 启用实际品类（port_dir/declaration/parameter/assignment/
      genvar_integer/function/task + inst_port handler），替换注释模板
- [ ] **管线集成验证**：结构路径（Lex→边界扫描→引擎→输出）与主管线共存验证

## P2 — 工程化收尾（发布准备，不阻碍功能推进）

> 现状：`.github/` 为空目录、全库无 `ci.yml`（CI 曾存在后被 `38e2daf` 移除）；缺 CONTRIBUTING/CHANGELOG/API 文档；
> 建议在第二语言期间同步建立覆盖率基线，防止渗透回归。

- [ ] **覆盖率门禁**：恢复覆盖率测量脚本 + 目标 ≥90%（2026-07-25 P1 遗留）
- [ ] **恢复 CI**：`.github/workflows/ci.yml`（Windows + Python 3.11/3.12/3.13 矩阵，pytest + coverage）；
      前置：从 `.gitignore` 移除 `.github/`（当前规则导致 CI 无法被追踪）
- [ ] **安装可验证**：`pip install -e ".[test]"` 通过（pyproject 已建未验证，依赖管理评估遗留）
- [ ] **补文档**：CONTRIBUTING、CHANGELOG、API 文档（docs/ 现有 12 文件缺这三项）

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
