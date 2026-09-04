# Gap — 语义/插件契约边界（elaboration / 深语义 / invert 嵌套 / 注册表 / 版本）

- 状态：混合——接受（设计/工程摩擦）+ 待闭环（invert 嵌套，TODO P1.5）
- 关联：原 `docs/known_limitations.md` Scope/Engineering 边界（2026-09-04 按
  部件拆入本档）；ADR-0008；`grammar/verilog/plugins/typed_ports/`
- 参照：Verilator 的 elaboration/宽度传播模型

## 边界是什么

1. **Elaboration 按工程非全设计**（接受 + 已跟踪 ADR-0008 P2.7）：跨模块检查
   （模块注册表/端口连接展开/信号驱动负载图/实例树驱动穿透）覆盖被检入口 +
   发现依赖；非全设计 elaboration——无未选分支的 elaboration 期 generate 语义
   （超出内建求值器）、无数值宽度传播（Verilator 式）、无 CDC 分析。
2. **深语义在插件代码非 TOML**（接受）：配置驱动语法/渲染/浅语义（作用域/
   符号/名字解析）；真正新语义能力 = 引擎原语/插件脚本；表达式树形态
   （`UnaryOp`/`BinaryOp`）+ 内建前缀运算符是引擎约定，语言包须对齐非全自由
   数据。
3. **invert 嵌套/ref 端口部分展开**（待闭环，TODO P1.5 L2-L3 未修）：
   `type wrap { master: spi.master inner, input enable; slave: invert master; }`
   的反转角色的嵌套展开端口（`inner_*`）不参与方向反转，仅普通端口参与。
   管线防御不泄漏字面 `SKIP`（空行从映射表过滤 + 无输出结果在 expand 丢弃），
   输出是合法 Verilog 但嵌套反转端口静默缺失。完整展开需 resolve 时取反转
   角色的**合并端口集**（plain + refs）。
4. **GrammarRulesRegister 进程全局单例**（工程摩擦，接受）：一进程加载两个
   语言包混合规则；测试用独立注册表，嵌入式切换语言须同样处理。
5. **Inject 多规则同目标加深传播嵌套**（工程指引）：逐规则注入每次包一层；
   插件作者应把注入语句归组到容器规则（`plugins/sim` 的 `SimCtrlStmt`）。
6. **语言包未版本钉住引擎**（工程摩擦）：包依赖引擎语义（FOLLOW 推导/inject/
   节点绑定）；引擎改动靠测试守门，非包/引擎版本契约——升级引擎可能破坏旧包。

## 为什么是边界（影响面）

1/2 是"前端规范执行而非全设计语义"的定位延伸（elaboration 深度留给自研
插件/外部工具）；3 是真实功能缺口（typed_ports 组合形态）；4/5/6 是嵌入/
多语言/升级场景的工程摩擦。

## 成熟解法参照（见贤思齐）

- 1 宽度传播：Verilator 数值宽度传播是参照（但属"全设计 elaboration"，tpc
  不做——若需深度宽度/CDC，接外部 oracle 是 gap-tpc-check 的方向）。
- 3：需 resolve 期合并端口集（typed_ports `_transform.py` 已有 `_file`/
  端口方向集上下文可扩）。

## 可实现性

- 3：typed_ports resolve 阶段对 invert 角色取 plain + refs 合并端口集再做方向
  反转——插件内改动 + cases 样例回归（TODO P1.5）。
- 4/5：文档约定（独立 registry/容器规则），已有测试与 sim 插件先例。
- 6：若需版本契约 → pack 声明 engine 兼容范围 + 加载 fail-fast 校验（低成本
  扩展，未立项）。
- 1/2：不改（范围）。

## 关联条目

- ADR-0008（elaboration per-project，P2.7）
- TODO P1.5（typed_ports invert L2/L3）
- `grammar/verilog/plugins/typed_ports/` + `analyzer/checker.py::ProjectChecker`
- 原 `docs/known_limitations.md`（Scope elaboration/deep-semantics +
  Engineering invert/singleton/inject/version-pin）
