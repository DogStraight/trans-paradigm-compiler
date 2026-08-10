# TODO

## 1. 工程化的基础设施（2026-08-10 立项）

> 现状：`pyproject.toml`（build-system/project/scripts/optional-deps/pytest/coverage）与 LICENSE 已落地；
> `.github/` 为空目录、全库无 `ci.yml`（CI 曾存在后被 `38e2daf` 移除）；缺 CONTRIBUTING/CHANGELOG/API 文档；
> 2026-07-25 质量评估遗留 P0/P1（异常层级、覆盖率门禁）。

- [ ] **恢复 CI**：`.github/workflows/ci.yml`（Windows + Python 3.11/3.12/3.13 矩阵，pytest + coverage）；
      前置：从 `.gitignore` 移除 `.github/`（当前规则导致 CI 无法被追踪）
- [ ] **安装可验证**：`pip install -e ".[test]"` 通过（pyproject 已建未验证，依赖管理评估遗留）
- [ ] **覆盖率门禁**：恢复覆盖率测量脚本 + 目标 ≥90%（2026-07-25 P1 遗留）
- [ ] **异常层级统一**：统一异常体系 + 清理 except 吞噬 + TOML 模式验证（2026-07-25 P0 遗留）
- [ ] **补文档**：CONTRIBUTING、CHANGELOG、API 文档（docs/ 现有 12 文件缺这三项）
- [ ] **自定义 DSL 完整示例**：用本套配置化体系从零定义一个小语言（规则 TOML + 插件 +
      最小用例 + 跑通全管线），作为外部贡献者上手参考——展示"语言知识全外部化"能力，
      降低想拿本项目当骨架/改造的人的入门门槛（当前文档全围绕 Verilog，缺"从零搭语言"的 walkthrough）
- [ ] **调试基础设施**（parser + linter 共用，当前最难调试的两个模块）：
      a) 日志分级开关（ERROR/WARN/INFO/TRACE，修复 `debug_log_file=None` 时 `_log_state`
         变空操作导致 WARN 全被吞的问题——本会话多次踩坑）；
      b) parser 停点/trace（`_failure_attempts` 已有雏形，扩展为按 token 位置/规则名过滤、
         parse 中途可查 `token_pointer` 停点）；
      c) discovery 节点树 token 区间 dump（节点 rule + [start,end) → 行号）；
      d) 行号对账工具（token 1-based line vs token_span 0-based vs 物理行内容）

## 2. 预处理器增强（2026-08-10 立项）

> 现状：已有 define/ifdef/include/undef primitives + `_expand.py`/`_reverse.py`；
> 已修复嵌套 ifdef inactive 祖先、续行拼接、include 配置化；
> 行首未知指令当前被 scan_directives 整体删除（跨子系统容错边界）。

- [ ] **管线内宏 token 决议**：行内宏调用在预处理器阶段展开/决议，管线内不再残留宏 token
      （linter P0 保险措施的前提；当前 e12 靠行内宏调用做 undefined-macro 可达性验证）
- [ ] **未知/错误指令容错**：行首未知指令从"整体删除"改为可配置策略 + 诊断报告（保留容错）
- [ ] **带参宏支持**（如 `` `define NAME(a,b) ... ``）：评估参数展开（当前仅文本替换）
- [ ] **预处理器单元测试**：指令原语/宏展开/ifdef 分支/逆向恢复（当前零测试，后续按部件分文件补充）

## 3. 格式化插件完善（2026-08-10 立项）

> 现状：品类系统框架完成（boundary/engine/grouping/passes）；
> `formatter/tpc.toml` 品类配置仍为注释模板；无单元测试（逻辑验证靠人工）；
> boundary.py 存在 keyword.*→ScopeKind 语言渗透（待立项）。

- [ ] **品类配置落地**：tpc.toml 启用实际品类（port_dir/declaration/parameter/assignment/
      genvar_integer/function/task + inst_port handler），替换注释模板
- [ ] **formatter 单元测试**：边界扫描器/分组/品类引擎/passes（当前零测试，后续按部件分文件补充）
- [ ] **boundary.py 语言渗透消除**：keyword.*→ScopeKind 映射外部化到配置（遵守"不编码语言知识"铁律）
- [ ] **管线集成验证**：结构路径（Lex→边界扫描→引擎→输出）与主管线共存验证

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
