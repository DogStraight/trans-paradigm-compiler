# Gap — 语义/插件契约边界（elaboration / 深语义 / 注册表 / 版本）

- 状态：接受（1/2 范围设计选择；3/4 工程摩擦——机制已备）
- 关联：`analyzer/checker.py::ProjectChecker`（elaboration 三层）；
  `grammar/verilog/plugins/typed_ports/`；`core/config_lifecycle.md`
- 参照：Verilator 的 elaboration/宽度传播模型

## 边界是什么

1. **Elaboration 按工程非全设计**（接受）：
   跨模块检查（模块注册表/端口连接展开/信号驱动负载图/实例树驱动穿透）覆盖
   被检入口 + **按实例化链发现**的依赖文件。未覆盖：
   - 同工程但既不在依赖链、也不在「入口所在目录 / include 目录」内的文件
     （查找策略：同名文件优先 → 目录内关键字文本扫描兜底；跨目录需多入口
     `check(paths)` 或 include 声明）
   - 全设计 elaboration：无未选分支的 elaboration 期 generate 语义（超出内建
     求值器）、无全设计数值宽度传播（Verilator 式）——宽度语义按需由
     `checks/width_check` 覆盖（W201 赋值/端口截断、W202 位选越界；参数化
     折叠 + 层次成员宽度）；无 CDC 分析
2. **深语义在插件代码非 TOML**（接受）：配置驱动语法/渲染/浅语义（作用域/
   符号/名字解析）；真正新语义能力 = 引擎原语/插件脚本；表达式树形态
   （`UnaryOp`/`BinaryOp`）+ 内建前缀运算符是引擎约定，语言包须对齐非全自由
   数据。
3. **全局可变单例（注册表/配置/组件表）**（工程摩擦，机制已备）：
   GrammarRulesRegister / ConfigRegistry / plugin_loader 进程级、只增不重置
   ——同进程多语言/多配置切换需独立实例或经 `core/global_state.py`
   snapshot/restore 清理（测试已自动化：conftest 每测试还原，顺序无关）。
4. **Inject 多规则同目标加深传播嵌套**（工程指引）：逐规则注入每次包一层；
   插件作者应把注入语句归组到容器规则（`plugins/syntax/sim/` 的
   `SimCtrlStmt`）。

## 为什么是边界（影响面）

1/2 是"前端规范执行而非全设计语义"的定位延伸（elaboration 深度留给自研
插件/外部工具）；3/4 是嵌入/多语言场景的工程摩擦。

## 成熟解法参照（见贤思齐）

- 1 宽度传播：Verilator 数值宽度传播是参照（但属"全设计 elaboration"，tpc
  按需覆盖（`checks/width_check`，见边界 1）——更深宽度/CDC 接外部 oracle
  （gap-tpc-check 方向）。

## 可实现性

- 3/4：机制已备（全局状态快照/还原 `core/global_state.py`；注入归组容器
  规则），已有测试与 sim 插件先例。
- 1/2：不改（范围）。

## 关联条目

- `grammar/verilog/plugins/typed_ports/` + `analyzer/checker.py::ProjectChecker`
