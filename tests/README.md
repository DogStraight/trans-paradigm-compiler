# tests/ — 测试分层

配置驱动的语言流水线（引擎）测试树。零运行时依赖；pytest 默认并行
（`-n auto --dist loadfile`，见 pyproject addopts），串行/收集用 `-n 0`。
各层规模不写死在本文（不造复述点）：以 `pytest --collect-only -q` 实测为准。

## 分层

| 层 | 命令 | 定位 |
|----|------|------|
| smoke（快速层） | `python -m pytest -m smoke` | 各功能域代表测试，日常/改动后快速回归 |
| 全量 | `python -m pytest tests/` | 发布/大改后完整回归 |

smoke 不代表全量——只覆盖每功能域核心路径，特性面全覆盖由全量兜底。
改动节奏建议：小改动跑 smoke（+ 涉及子系统专项）；结构性/跨子系统改动跑全量。

## smoke 组别与代表（`@pytest.mark.smoke`）

| 组别 | 代表 | 打标粒度 |
|------|------|----------|
| core（配置 fail-fast） | `engine/core/test_config_loading.py` | 模块级 |
| lexer（基础 token 化） | `engine/lexer/test_lexer.py::TestTokenizeBasic` | 类级 |
| parser（Pratt 框架） | `engine/parser/test_pratt_parser.py` | 模块级（纯合成零依赖） |
| linter（P1 边界） | `engine/linter/test_linter_boundary.py::TestNormalBoundary` | 类级 |
| analyzer（Scope/Symbol） | `engine/analyzer/test_analyzer.py` | 模块级（纯单元） |
| transform（注释迁移） | `engine/transform/test_comment_migrate.py::TestMigrateComments` | 类级 |
| renderer（渲染原语） | `engine/renderer/test_renderer_primitives.py` | 模块级（fake renderer 纯内存） |
| preprocessor（宏指令） | `engine/preprocessor/test_primitives.py` + `test_macro_shape.py` | 模块级 |
| pipeline（时点序列） | `engine/pipeline/test_schedule.py::TestSequenceEntries` + `TestBuildSchedules` | 类级 |
| languages/verilog | `languages/verilog/test_real_syntax.py` + `test_tok_span.py` | 模块级 |
| languages/c4（第二语言） | `languages/c4/test_c4_asm.py::TestC4Assembly` | 类级 |
| languages/yaml | `languages/yaml/test_yaml_plain.py::TestPlainValueForms` | 类级 |
| e2e real_corpus | `test_real_corpus.py` 的 `ref_uart_rx.v`（非 sv-parser 断言） | 参数级（`_SMOKE_CORPUS`） |
| e2e macro_reverse | `test_macro_reverse.py::test_func_macro_basic_reversed` | 函数级 |
| e2e comment_restore | `test_comment_restore.py::TestCommentsSample::test_all_comments_survive` | 函数级 |
| e2e comment_container | `test_comment_container.py::TestBlockEndComments::test_end_line_comment_kept` | 函数级 |
| e2e enhanced_render | `test_enhanced_render.py::test_expand_path_emits_basic_verilog` | 函数级 |
| e2e command_params | `test_command_params.py::test_commands_declared_as_params` | 函数级 |
| e2e pipeline_idempotent | `test_pipeline_idempotent.py::test_non_expanded_idempotent` | 函数级 |
| policy（D1-D4 门禁） | `policy/test_check_doc_refs.py` | 模块级（含真仓库回归） |

## 代表维护规约

- **新增/改动功能**：若属某组核心路径，把该组代表性测试标 `@pytest.mark.smoke`
  （测试文件顶部注释标组归属）；边缘行为不必进 smoke（全量兜底）。
- **smoke 预算 ~1 分钟**：总时长超预算时，优先收窄过重代表
  （整文件 → 类级 → 参数级子采样，参考 real_corpus `_SMOKE_CORPUS`/`_corpus_params`）。
- **真实语料子采样**：real_corpus 全 9 语料昂贵（tv80/ice40 单断言 20~60s），
  smoke 只抽轻量 `ref_uart_rx`——module 级结果缓存保证只跑它 1 次全管线，
  3 个非 sv-parser 断言共享；sv-parser 差分断言不进 smoke（外部二进制 + 慢）。
- marker 注册见 pyproject `[tool.pytest.ini_options].markers`。

## 隔离与顺序巡检

测试隔离机制见 `core/global_state.py`（登记表 + 两层还原）与
`tests/policy/test_global_state_coverage.py`（新增全局态不登记即红）。
顺序敏感（“幽灵 flake”）靠下列两档把偶发变必现：

| 维度 | 日常档 | 巡检档 |
|------|--------|--------|
| 执行顺序 | 默认收集序（`--dist loadfile` 保证一个文件在同一 worker） | `TPC_SHUFFLE_SEED=<int>` 文件级乱序（种子固定 → 失败可复现） |
| 哈希种子 | `PYTHONHASHSEED=0`（CI 已设；失败可复现） | 不设 = 每进程随机（nightly）——集合/字典序敏感问题仅此档暴露 |

```bash
`$env:TPC_SHUFFLE_SEED="1"; python -m pytest tests -q`   # 全量乱序（复现同一失败用同一 seed）
```

乱序粒度是**文件**：模块级/session 级 fixture 在其作用域内合法拥有语言安装态，
单用例级乱序会把作用域反复拆开重建（那是 fixture 语义问题，不是隔离缺口）。
跨文件顺序才是 xdist 分发可变面。

### 进程级隔离（对照工具）

```bash
python tools/check_test_isolation.py --compare            # 全量：每文件一进程 + 单进程对照
python tools/check_test_isolation.py --compare -m smoke   # 快速层（nightly 跑这档）
python tools/check_test_isolation.py --granularity test tests/e2e/test_real_fidelity.py
```

把选中集切块（默认每文件一块）在**全新解释器**里各跑一遍，再与**单进程共享档**
（刻意 `-n 0`：xdist 会把文件分到不同 worker，那样“共享”名不副实）对照，列出
两个方向的差异：

- **只在共享档失败** = 进程内状态泄漏 / 顺序污染（补 `core/global_state.py` 登记表，
  或改 fixture 作用域）；
- **只在隔离档失败** = 该用例隐式依赖同进程里其它文件留下的状态（CI 分片、单文件
  重跑、换 `--dist` 时同样会爆）。

细节：不用 `pytest-forked`（它走 `os.fork`，Windows 没有）；`--granularity test`
是单用例一进程（最强隔离，慢）；全量隔离档与并行全量同量级（分钟级），
共享档单进程要跑全集（近十分钟）——故工具不进日常门禁，自保用例见
`tests/policy/test_check_test_isolation.py`（含“真能报出差异”的负例）。

## 并发注意

- 全局 `timeout=120`（pyproject）：并行 CPU 争抢使真实语料全管线慢 ~2.5x
  （tv80 单跑 24s → 并行 60s+）。60s 阈值在并行下触发 pytest-timeout → thread
  与 xdist worker 交互崩溃（`Not properly terminated`；串行无争抢不触发）。
- 串行验证用 `-n 0`（规避 xdist 收集/并行争抢）；真实语料行为用
  `python -m pytest tests/e2e/test_real_corpus.py` 并行复现。
