# grammar — 语言规则（数据，语言知识不进引擎代码）

> 引擎语言无关的载体：语言包（TOML 语法规则 + 插件目录）。从零搭一门语言教程见
> `docs/language_walkthrough.md`（c4 实例）。
> 语法规则字段参考（schema/字段含义/常见形态）见 `grammar/grammar_rule_fields.md`；
> 加语法结构/扩展组件的工作流见 `core/component_protocol.md`（inject 挂载 + 组件协议）。

## 语言包

| 语言包 | 一句话 |
|------|--------|
| `verilog/` | Verilog-2005 主体语言包（主包 = 可综合子集，发布基线） |
| `c4/` | 从零搭语言实例（迷你 C，产出汇编；language_walkthrough 教程主角） |
| `yaml/` | YAML 语言包（缩进 token 机制 + 块标量/plain scalar 验证） |

## verilog 插件族（`grammar/verilog/plugins/`）

| 插件族 | 一句话 |
|------|--------|
| `syntax/` | 语法扩展：sim（仿真语句）/ gates / nettypes / udp / specify / configs / attributes |
| `formatter/` | 世界 B：pass 管线 formatter（对拍 Verible，独立于世界 A） |
| `checks/` | 检查规则插件族：name/width/latch/unused/inst/hier/case/always/semantic（NC/W/AW 等码族） |
| `typed_ports/` | 自定义类型化端口（impl/type 声明 + 展开变换） |

> 加语法结构见 `core/component_protocol.md`（inject 挂载 + 组件协议）；加检查规则见
> `grammar/verilog/plugins/checks/`（L1 声明式 [[checks]] 规则表 + L2 handler 脚本，
> name_check 为最小示例）。

## 扩展已有语法（inject 归组）

扩展语法用 `[ExtRule.inject] targets = ["@TargetRule"]`（或 `TargetRule.production[N]`）
挂到已有规则上；引擎做法是**两层注入**——直接注入 + 传播注入（引用 @Target 的规则
替换为 `(@ExtRule|@Target)`），实现见 `parser/grammar_inject.py`。

⚠ **多条规则注入同一 target 时，先归组到容器规则、再注入一次**：传播注入会把引用
`@Target` 的规则逐条替换为 `choice[@Ext, @Target]`，各自 inject 会让嵌套按规则数线性
加深；且单例规则表被 `_write_prods` 污染后每次 `setup_grammar` 叠加 → 全量测试深到
serialize `RecursionError`。先例：`grammar/verilog/plugins/syntax/sim/90_sim_ctrl.toml`
（各仿真语句先挂 `SimCtrlStmt`，容器再注入 `@CtrlStmt` 一次）；机制边界见
`docs/gaps/gap-semantic-elaboration-boundaries.md`。
