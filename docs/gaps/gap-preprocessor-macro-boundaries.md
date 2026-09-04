# Gap — preprocessor 宏覆盖缺口（type macros / 复合嵌套反向映射）

- 状态：待闭环（已跟踪 TODO「宏系统剩余」类；未立项细化）
- 关联：原 `docs/known_limitations.md` Correctness boundaries（2026-09-04 按
  部件拆入本档）
- 参照：C 预处理器（对象/函数宏 + 条件编译）的成熟形态

## 缺口是什么

宏系统覆盖常用形式，非全种类：对象/函数式 `` `define ``、条件编译
（`ifdef/ifndef/else/elsif/endif`）、`` `include ``（递归、循环检测）、反斜杠
续行——均支持，且带反向映射回原文。两个剩余缺口：

1. **type macros 不全支持**：宏展开为类型/声明形态的宏（"类型宏"）未覆盖。
2. **复合嵌套宏调用反向映射可能失败**：展开器把复合嵌套宏调用折叠为单 token，
   无整词匹配的词边界——`_reverse` 无法干净还原。

## 为什么是缺口（影响面）

真实工程（如 PicoRV32 类核心）会混用"声明/类型宏 + 嵌套调用"，反向映射失败
意味着展开路径的输出与源保真打折（往返 diff 需容差）。当前 real 语料门禁锁定
已覆盖形态，嵌套宏是剩余攻击面。

## 成熟解法参照（见贤思齐）

- C 预处理器对宏展开做 token 级保留（预扫描标记），反向映射的成熟做法是展开
  期保留"宏调用区间"结构，而非折叠后猜词边界。
- `preprocessor/_bridge.py`（锚 + 残片回插）已是统一位置桥——type macro 可沿
  该桥扩展"声明形态宏"的锚记。

## 可实现性

- 反向映射：展开期对复合调用保留调用树/区间锚（而非折叠单 token），`_reverse`
  沿锚还原——需 preprocessor 展开器改动 + real 语料嵌套宏样例回归。
- type macros：在 `` `define `` 展开后按"目标槽位（类型位）"再解析声明形态，
  形态有限（端口/参数类型），可增量加。
- 验证：`tests/languages/verilog/test_macro*.py` + real 语料宏还原门禁
  （`tests/e2e/test_macro_reverse.py`）。
- 依赖前置：无（纯 preprocessor 层）。

## 关联条目

- 原 `docs/known_limitations.md`（Correctness：macro system covers common forms）
- `preprocessor/`（`_expand.py`/`_reverse.py`/`_bridge.py`）
- real 语料宏还原门禁：`tests/e2e/test_macro_reverse.py`
