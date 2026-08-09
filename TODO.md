# TODO

## 1. 工程化的基础设施（2026-08-10 立项）

> 现状：`pyproject.toml`（build-system/project/scripts/optional-deps/pytest/coverage）与 LICENSE 已落地；
> `.github/` 为空目录、全库无 `ci.yml`（CI 曾存在后被 `38e2daf` 移除）；缺 CONTRIBUTING/CHANGELOG/API 文档；
> 2026-07-25 质量评估遗留 P0/P1（异常层级、覆盖率门禁）。

- [x] **tests/ 单元测试按部件归档**（2026-08-10）：16 个测试文件从平铺 `tests/` 根归档到
      `tests/{linter,parser,lexer,analyzer,renderer,core}/`，`conftest.py`/`__init__.py` 留在根；
      329 全绿（修复：子目录不建 `__init__.py` 防遮蔽项目根同名牌；`test_lint_accuracy._ROOT` 上移一层）
- [ ] **恢复 CI**：`.github/workflows/ci.yml`（Windows + Python 3.11/3.12/3.13 矩阵，pytest + coverage）；
      前置：从 `.gitignore` 移除 `.github/`（当前规则导致 CI 无法被追踪）
- [ ] **安装可验证**：`pip install -e ".[test]"` 通过（pyproject 已建未验证，依赖管理评估遗留）
- [ ] **覆盖率门禁**：恢复覆盖率测量脚本 + 目标 ≥90%（2026-07-25 P1 遗留）
- [ ] **异常层级统一**：统一异常体系 + 清理 except 吞噬 + TOML 模式验证（2026-07-25 P0 遗留）
- [ ] **补文档**：CONTRIBUTING、CHANGELOG、API 文档（docs/ 现有 12 文件缺这三项）

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

## linter 边界问题（后置，不阻塞全绿）

> 发现器多层级化 + 两级消歧完成后暴露的边界问题（用户明确：接受误报，边界管理，
> 此清单后置处理，不阻塞当前全绿状态）。

- [ ] **表达式内运算符后换行（多行 RHS）误报**：`a <= b +\n c;` 中 `+` 后换行被 pratt 视为表达式终止
  - 根因：`parser/pratt_parser.py` 无 newline/trivia 跳过逻辑（表达式不跨行）
  - 影响：`a = b +\n c;`、`a <= (b +\n c);` 等运算符后换行被误报 "expected ';' got 'id'"
  - 方案：pratt 解析时跳过 newline（或 linter 表达式检查预折叠换行），需评估对 parser 主流程影响
- [ ] **`always @*` 敏感列表误判**：`always @* begin` 中 `@*` 被当 `@(` 期待括号（`test_nested_begin_end` 相关）
  - 根因：`@` 后 `*`（symbol.base.multiple）与 `@(...)` 的消歧边界
- [ ] **while/repeat 语句无完整语法规则**：`while`/`repeat` 已定义为关键字（token.toml），
  - 但 grammar 无对应语句规则（RepeatStmt/WhileStmt），发现器跳过其内部（body 语句仍被发现）
  - 方案：如需检查 while/repeat 结构，补充对应语法规则（语法扩展，非 linter 改动）
- [x] **function 有范围头漏检**：`function [7:0] add(...)` 的 `@Range?` 非原子 call 截断判别
  - 根因：`_feat_token_paths` 对非原子 call（@Range 等在判别点前）返回 None 截断，丢 first 集
  - **已修复（2026-08-02）**：`_feat_token_paths` 对 first 含 `[` 的可选复杂 call（@Range?）保留
    epsilon + first 集（可被 Level 1 括号配对跳过）；其他（@ParamOverride? 的 `#(...)`）维持
    截断走 Level 2。验证：`function [7:0] add` 发现 FuncDecl，normal/errors 全过。
- [x] **带下标赋值目标漏检**：`data[i] = i;`（for/always 内）的 `data[` 首判别 token 是 `[`
  - （select），B 类 paths 只认 `=`/`<=`/`(` → 语句不发现
  - **已修复（2026-08-02）**：Level 1 前瞻遇 `[` 用括号配对跳过区间（`_skip_square`，语言无关，
    不依赖 `_match_select`）；残缺 `data [i = i` 括号未闭合→跳过失败→保守淘汰不吞错。
    验证：`data[i] = i` 发现 BlockingAssign，`a[3:0] = b` 亦修复，ModuleInst 无回归。

## 设计说明（已落地，供参考）

- 发现器多层递归最多到句子级；句子结束符由 production 结尾字面 token 推导（`_derived_end_case`），
  仅非容器规则推导，不往 end_case 加值（end_case 配置零改动）
- A/B 类消歧统一为动态两级（2026-08-02）：Level 1 变长前瞻（前缀路径，**公共前缀匹配**——
  seen 与路径双向前缀一致，允许 seen 比路径短）+ Level 2 试解析（复用 RuleMatcher，limit 含终止符）
- 块规则（task/function）在 lookahead 构建时**还原 block_start** 到 production 首，与普通 A 类
  规则视图统一（prods[0] 都是触发 token，paths 统一从 prods[1:] 开始）
- 前瞻深度上界 = 语句边界块；候选清空 → 暂返回 None（未识别语法报告待增强）
