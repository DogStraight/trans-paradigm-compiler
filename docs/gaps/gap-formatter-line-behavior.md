# Gap — formatter（世界 B）行行为边界（宽度折行 / 保留行 / 对齐 / 幂等）

- 状态：混合——设计选择（保留行/宽度折行）接受；对齐/折行细节为摩擦
- 关联：原 `docs/known_limitations.md` Correctness/Engineering 边界（2026-09-04
  按部件拆入本档）；`grammar/verilog/plugins/formatter/README.md`（世界 B 架构）
- 参照：verible-verilog-format / clang-format 的折行与对齐策略

## 边界是什么

1. **折行基于宽度非语义**（接受）：formatter 只在语法安全点折超长行（>100 列，
   惩罚模型，Verible 式）；不做段落实体式重排（不像段落格式化到目标宽）。
2. **保留行结构**（接受）：重新缩进/对齐/折超长，但**永不合并行、不插空行**——
   输出结构源于输入既有行。风格配置编码并经保真基线校验，非硬编码单一 house
   style。
3. **幂等只在保留路径保证**（接受）：展开路径（宏展开/transform）内容按设计
   变化，不幂等检查。
4. **品类对齐跳过多声明器行**（摩擦）：`reg [1:0] state, next;` 原样保留，
   只对齐单声明器行。
5. **宽度折行留下部分超长结构不折**（摩擦）：无顶层安全断点的超长拼接等
   不折行。

## 为什么是边界（影响面）

- 1/2/3 是刻意设计（保真优先：输出结构跟随输入行，折行只在安全点）——用户
  期望"合并紧凑行"或"语义重排段落"时不满足，但换来源结构稳定 + 可对拍
  （vs Verible 差分门禁）。
- 4/5 是折行/对齐算法的已知空档（无安全断点/多声明器粒度）——超长或并列
  声明场景格式化不彻底，但输出仍合法。

## 成熟解法参照（见贤思齐）

- clang-format 对声明器列表/超长表达式的折行（`binpack`/`AlwaysBreakAfter`）
  是对齐 4/5 的参照方向（世界 B pass 内，非引擎改动）。
- verible 差分门禁（`tests/differential/run_differential.py`）已是对拍裁判。

## 可实现性（若要改）

- 4：品类对齐 pass 增加多声明器拆分对齐（参照 sv-parser/verible 对齐列）。
- 5：wrap pass 增加"拼接体无安全断点"的兜底（如逗号/运算符后强制断点）。
- 1/2/3：设计选择，不改（接受；如需段落式重排属新能力，非修复）。
- 验证：`tests/languages/verilog/test_formatter*.py` + vs Verible 差分 + e2e
  幂等门禁。

## 关联条目

- `grammar/verilog/plugins/formatter/README.md`（世界 B：数据流/带结构行/
  引擎内建遍）
- 原 `docs/known_limitations.md`（Correctness line wrapping / preserves /
  idempotence + Engineering column-align / wrap-leaves）
- 差分对拍：`tests/differential/run_differential.py`
