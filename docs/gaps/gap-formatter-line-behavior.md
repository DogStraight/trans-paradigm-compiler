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
3. **幂等只在保留路径保证**（接受）：展开路径（宏展开/transform）内容按设计
   变化，不幂等检查。
4. **宽度折行留下部分超长结构不折**（摩擦）：无顶层安全断点的超长行不折——
   179 字符单标识符行原样保留；有 `+`/`,` 断点的超长行正常折（在 96 列断行）。
   属可接受空档（输出合法）。
5. **折行后带注释行的 init 重拼空格**（摩擦，既存）：带行尾注释的长行首遍被
   列对齐跳过（注释保护），wrap 拆行后**无注释的头段**在二遍 format_source 里
   进入列对齐——init token 重拼（`_parse_decl_parts` 的 `" ".join`）给 concat
   内 `,` 前补一格（`{ RESMODE, 4'd0 }` → `{ RESMODE , 4'd0 }`）；二遍后收敛
   （t2 == t3，非振荡），输出合法、仅空白差异。

## 为什么是边界（影响面）

- 1/2/3 是刻意设计（保真优先：输出结构跟随输入行，折行只在安全点）——用户
  期望"合并紧凑行"或"语义重排段落"时不满足，但换来源结构稳定 + 可对拍
  （vs Verible 差分门禁）。
- 4 是空档而非缺陷（无断点超长行不折，但输出合法）；5 是空档（折行头段
  一次性补空格，二遍收敛）。

## 成熟解法参照（见贤思齐）

- clang-format 对声明器列表/超长表达式的折行（`binpack`/`AlwaysBreakAfter`）
  是对齐 4 的参照方向（世界 B pass 内，非引擎改动）。
- verible 差分门禁（`tests/differential/run_differential.py`）已是对拍裁判。

## 可实现性（若要改）

- 4：wrap pass 增加"拼接体无安全断点"的兜底（如逗号/运算符后强制断点）。
- 5：init token 重拼加标点邻接规则（`{`/`,`/`}` 邻接不补空格）；改动牵动
  所有 init 行空白输出，需单独评估影响面后再动。
- 1/2/3：设计选择，不改（如需段落式重排属新能力，非修复）。

## 关联条目

- `grammar/verilog/plugins/formatter/README.md`（世界 B：数据流/带结构行/引擎内建遍）
- 实现：`grammar/verilog/plugins/formatter/passes/column_align.py::run_category_pass`
- 门禁：`tests/languages/verilog/test_formatter*.py` + `test_column_align.py`
  （含重组输出断言，漂移形态 `,\s{2,}<ident>`）+ vs Verible 差分（
  `tests/differential/run_differential.py`）+ e2e 幂等门禁
