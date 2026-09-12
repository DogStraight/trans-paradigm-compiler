# Gap — 验证与工程边界（sample-driven / 吞吐 / IDE / 增量 / hash / 覆盖）

- 状态：接受（技术权衡/门禁事实）+ 已跟踪（incremental → ROADMAP P3.x）
- 关联：原 `docs/known_limitations.md` Architecture/Engineering 边界（2026-09-04
  按部件拆入本档）；ROADMAP P3.1/P3.2/P3.4
- 参照：编译器的增量编译/LSP 服务模型

## 边界是什么

1. **验证 sample 驱动非穷举**（接受 + 摩擦）：正确性依赖精选语料（单元/真实
   核/recall 门禁）。差分测试存在（sv-parser 98 文件 / Verible 136 / 四工具
   lint 共识）；fuzz harness 接入 CI，但随机合法程序的 fuzz 覆盖**未统计化**
   （P2.3 fuzz 吞吐项）。
2. **吞吐解释器受限**（接受）：31 文件 / ~5.2k token 语料实测 lexer ~183k
   tok/s、parser ~21k tok/s、合并 ~19k tok/s——比原生编译器慢 50–500×，解释型
   Python + 通用回溯的固有成本。适合单文件/中小工程，非整仓库/超大文件工具。
3. **无 IDE/LSP**（接受）：CLI 管线，非编辑器插件（LSP 是另一分发形态）。
4. **无优化 pass**（接受）：transform 是配置驱动结构重写（类型展开/宏处理），
   非 LLVM 式优化。
5. **无增量解析**（已跟踪）：每次运行全量重解析。增量解析 + 增量检查（span
   绑定/失效/重解析）是 ROADMAP P3.1/P3.2/P3.4（v0.2 core）。
6. **Transform 包装实例名带 hash 后缀**（摩擦；**2026-09-12 实测修正**）：
   `u_spi_master_acb99d` 由 `md5(模块名 + 接口 + 类型 + role)[:6]` 生成
   （`grammar/verilog/plugins/typed_ports/_transform.py`）——**同输入可复现**，
   非"不稳定"：transform 组 X 路径实测保真 **1.0000**（与入库 golden
   `trans_spi_inf.v` 逐字一致）。真实摩擦只是：golden 里出现不可读魔法串，
   盐组成一改即全量失效；e2e 阈值 `0.95` 的注释"实例名 hash 差异可容忍"
   因此是**过度保守**（可收紧，非缺陷）。
7. **测试/覆盖门禁真实但非穷尽**（门禁事实）：覆盖 ~83%（`fail_under` 80），
   transform/renderer 最薄。
8. **列对齐/折行摩擦**：见 `gap-formatter-line-behavior.md`（该档为边界合集；
   多声明器对齐 2026-09-13 已修复，余为接受空档）。

## 为什么是边界（影响面）

1 决定"未测即可能错"的残余风险（fuzz 统计化收窄）；2 决定工具规模定位；3/4
是分发/范围选择；5 是大文件/重复调用场景的延迟瓶颈（v0.2 路线）；6/7 是
对拍/覆盖的可信度摩擦。

## 成熟解法参照（见贤思齐）

- 1 fuzz 统计化：csmith 式生成器 + 覆盖率引导（P2.3 已有吞吐方向）。
- 5 增量：编译器增量编译/LSP 失效模型是 ROADMAP P3.x 参照。

## 可实现性

- 1：P2.3 fuzz 吞吐 → 随机合法程序统计覆盖（见 ROADMAP/TODO 对应条目）。
- 5：ROADMAP P3.1/P3.2/P3.4（v0.2 core）——增量解析 + 增量检查，非短期。
- 2/3/4：接受（工具定位/范围）。
- 6：命名**已是确定性的**（实测）——若要 golden 可读，可改"确定性派生名"
  （如 `u_<module>_<role>`）或收敛盐组成并把它写进测试，需求驱动、非必须。
- 7：覆盖门禁持续收薄区（transform/renderer 测试补充），非独立缺口。

## 关联条目

- ROADMAP P2.3（fuzz 吞吐）、P3.1/P3.2/P3.4（增量，v0.2 core）
- `tests/fuzz/README.md`（语法驱动 + 变异 fuzzing，动机引自此边界）
- 原 `docs/known_limitations.md`（Correctness validation + Architecture
  throughput/no-IDE/no-opt/no-incremental + Engineering wrapper-hash/coverage）
