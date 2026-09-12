# Gap — preprocessor 宏覆盖缺口（type macros / 复合嵌套反向映射）

- 状态：待闭环（已跟踪 TODO「宏系统剩余」类；未立项细化）
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）
- 参照：C 预处理器（对象/函数宏 + 条件编译）的成熟形态

## 缺口是什么

宏系统覆盖常用形式，非全种类：对象/函数式 `` `define ``、条件编译
（`ifdef/ifndef/else/elsif/endif`）、`` `include ``（递归、循环检测）、反斜杠
续行——均支持，且带反向映射回原文。两个剩余缺口：

1. **类型位宏失败，语句位可用**（2026-09-12 实测收窄）：
   - ✅ **语句位可用**：`` `define REG_DECL reg [7:0] r0; `` + 模块体内
     `` `REG_DECL `` → 展开成功并还原（保真 0.972，无 marker 残留）；
   - ❌ **端口类型位失败**：`` `define PTYPE reg [7:0] `` + `input `PTYPE d` →
     展开留下 `tpc_marker_1` 占位，parser 在端口类型位无法解析
     （`success=False`，`parse truncated`）。
   故缺口实际是"宏落点在**类型槽位**时无对应锚/终结策略"，比原文"不全支持"
   更窄也更可操作。
2. **嵌套调用反向映射**（2026-09-12 实测**未复现失败**）：
   - 对象宏嵌套 `` `define B (`A + 1) `` → 保真 0.983；
   - 函数宏嵌套 `` `define V(y) `W(y)*2 `` → 保真 0.986；
   - 两者均无 marker 残留、`` `B `` / `` `V(3) `` 原样还原。残余差异全部来自
     与本缺口无关的 `module m;` → `module m();` 渲染归一。
   原描述"折叠单 token 后无法干净还原"在对象/函数两种嵌套形态上不成立——
   需另找触发形态（如宏体跨多语句 + 条件编译交织）再认定，否则应从缺口移除。

## 为什么是缺口（影响面）

真实工程（如 PicoRV32 类核心）会混用"声明/类型宏 + 嵌套调用"，类型位失败
意味着**端口声明里用类型宏写不出合法输入**（用户只能绕开），是真实的形态
盲区。原档并列的"嵌套反向映射失败"经实测未复现，暂不再作为缺口论据。

## 成熟解法参照（见贤思齐）

- C 预处理器对宏展开做 token 级保留（预扫描标记），反向映射的成熟做法是展开
  期保留"宏调用区间"结构，而非折叠后猜词边界。
- `preprocessor/_bridge.py`（锚 + 残片回插）已是统一位置桥——type macro 可沿
  该桥扩展"声明形态宏"的锚记。

## 可实现性

- 类型位宏：在 `` `define `` 展开后按"目标槽位（类型位）"再解析声明形态，
  形态有限（端口/参数类型），可增量加；先补"端口类型位"样例复现（已有最小
  复现，见上）。
- 嵌套反向映射：**先确认形态是否真的失败**（当前实测通过），确认后再谈
  保留调用树/区间锚的方案——不确认就不动展开器。
- 验证：`tests/languages/verilog/test_macro*.py` + real 语料宏还原门禁
  （`tests/e2e/test_macro_reverse.py`）。
- 依赖前置：无（纯 preprocessor 层）。

## 关联条目

- 原 `docs/known_limitations.md`（Correctness：macro system covers common forms）
- `preprocessor/`（`_expand.py`/`_reverse.py`/`_bridge.py`）
- real 语料宏还原门禁：`tests/e2e/test_macro_reverse.py`
