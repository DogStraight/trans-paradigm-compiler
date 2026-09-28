# Gap — formatter（世界 B）行行为边界（宽度折行 / 保留行 / 对齐 / 幂等）

- 状态：接受（设计选择 + 空档；见下各条）
- 关联：`grammar/verilog/plugins/formatter/README.md`（世界 B 架构）
- 参照：verible-verilog-format / clang-format 的折行与对齐策略

## 边界是什么

1. **折行基于宽度非语义**（接受）：formatter 只在语法安全点折超长行（>100 列，
   惩罚模型，Verible 式）；不做段落实体式重排（不像段落格式化到目标宽）。
2. **保留行结构**（接受）：重新缩进/对齐/折超长，但**永不合并行、不插空行**——
   输出结构源于输入既有行。风格配置编码并经保真基线校验，非硬编码单一 house
   style。
3. **幂等只在保留路径保证**（接受）：展开路径（宏表 / 占位符 / 指令行非空，
   `pipeline._check_idempotent` 判据）内容按设计变化，不幂等检查；其余路径
   （含 transform 输出）要求可被管线再次稳定解析。
4. **宽度折行留下部分超长结构不折**（摩擦）：无顶层安全断点的超长行不折
   ——单标识符行 / 超长字符串行原样保留；续行 / 端口列表 / 注释 / 指令行
   按设计跳过（ice40 语料未折超长行以此类为主）；有 `+`/`,` 断点的超长行
   正常折，断点列按惩罚模型选取（实测首段 5–97 列不等，非固定列）。属可
   接受空档（输出合法）。
5. **折行头段的 init 重拼空格**（摩擦，既存）：列对齐的 init 重拼
   （`_parse_decl_parts` 的 `" ".join`）给 concat 内 `,` 前补一格；wrap 拆行
   时只对头段做 concat 空格清理（` ,` → `,`）、尾段不清理。清理只在拆行
   那一遍生效——二遍头段（行已短、不再拆）重入列对齐，重拼的补格留存
   （`{ RESMODE, 4'd0 }` → `{ RESMODE , 4'd0 }`，darkriscv 实测 2 行：
   t1 → t2）；二遍后收敛（t2 == t3，非振荡），输出合法、仅空白差异。
6. **yaml 真实 workflow 的渲染不幂等**（摩擦，既存；**属 yaml 渲染器（世界 A）**，
   登记在此档因同属"行行为 / 幂等"族）：`tests/languages/yaml` 的
   `test_real_workflow_files_parse_and_roundtrip` 用本仓的
   `.github/workflows/ci.yml`；首遍把 `shell: pwsh` 之后的注释留在该行行尾，二遍
   把该注释**上提到前一行行尾**（实测文本 offset ≈ 2349：
   `… shell: pwsh\n  # 防止"editable 模式可用但 wheel 安装后 CLI 失败"…` →
   `… shell: pwsh # 防止…`）⇒ `format(format(x)) != format(x)`。
   现状：**与渲染器接线无关**（裸 `Renderer` 与生产接线 `line_comment_starts=…`
   下输出**逐字相同**、两遍都不幂等）；注释不丢、显著 token 序列逐项相同 ⇒ 属
   "位置漂移 + 一遍不幂等"，与 C 包缺口档 #6（行尾注释挂点随折行变化）同型。
   ⚠ **当前无门禁覆盖**：该用例只断言**结构往返**（`_node_names` 相等），不比对全文；
   `tests/e2e/test_pipeline_idempotent.py` 走 verilog 语料，不覆盖 yaml 这一形态。

## 为什么是边界（影响面）

- 1/2/3 是刻意设计（保真优先：输出结构跟随输入行，折行只在安全点）——用户
  期望"合并紧凑行"或"语义重排段落"时不满足，但换来源结构稳定 + 可对拍
  （vs Verible 差分门禁）。
- 4 是空档而非缺陷（无断点超长行不折，但输出合法）；5 是空档（折行头段
  一次性补空格，二遍收敛）；6 是空档（yaml 注释挂点随折行漂移，一遍不幂等；
  输出合法、注释与 token 都不丢）。

## 成熟解法参照（见贤思齐）

- clang-format 对超长表达式/参数列表的折行（`binpack`/`AlwaysBreakAfter`）
  是对齐 4 的参照方向（世界 B pass 内，非引擎改动）。
- verible 差分门禁（`tests/differential/run_differential.py`）已是对拍裁判。

## 可实现性（若要改）

- 4：wrap pass 增加"拼接体无安全断点"的兜底（如逗号/运算符后强制断点）。
- 5：init token 重拼加标点邻接规则（`{`/`,`/`}` 邻接不补空格）；改动牵动
  所有 init 行空白输出，需单独评估影响面后再动。
- 6：修点在注释挂点 / 折行交互（渲染器侧），**本轮不修**——yaml 侧当前没有
  全文幂等判据，且按"缺陷未修不许沉淀"的闸不先加样本；待单独一轮（先加判据
  证明红 → 再定修法）。与 C 包缺口档 #6 同族，可与其定案一并评估。
- 1/2/3：设计选择，不改（如需段落式重排属新能力，非修复）。

## 关联条目

- `grammar/verilog/plugins/formatter/README.md`（世界 B：数据流/带结构行/引擎内建遍）
- 实现：`grammar/verilog/plugins/formatter/passes/column_align.py::run_category_pass`
- 门禁：`tests/languages/verilog/test_wrap.py`（折行）+ `test_column_align.py`
  （含重组输出断言，漂移形态 `,\s{2,}<ident>`）+ `test_idempotent.py` + vs
  Verible 差分（`tests/differential/run_differential.py`）+ e2e 幂等门禁
  （`tests/e2e/test_pipeline_idempotent.py`）
- 条目 6（yaml）：`tests/languages/yaml/test_yaml_plain.py::TestRealWorkflowFiles`
  （只断言结构往返 ⇒ **无全文幂等门禁**）；harness 接线判据见
  `TestPlainRender::test_harness_renderer_keeps_line_comment_wiring`
