# core — 引擎骨架（配置注册、错误、插件加载、核心类型）

> 与语言无关的引擎底座：配置注册中心、插件加载、核心类型（Token/GrammarRule/
> Node）、错误层级、文档门禁工具入口。

| 文件 | 一句话 |
|------|--------|
| `define.py` | 核心类型：Token / GrammarRule / Node / FileManager；Node 树通用工具（`iter_nodes` / `unwrap_optional` / `collect_nodes`，引擎与语言包插件共用一份） |
| `config_registry.py` | 声明式配置注册中心（fail-fast 加载 + resolve） |
| `plugin_loader.py` | 插件加载与管理（capabilities / pass 声明 / postpass 收集） |
| `check_registry.py` | `[[checks]]` 声明式检查规则表（加载/校验/用户配置） |
| `token_protocol.py` | 引擎级 token 类型命名协议（单一事实源） |
| `_protocol.py` | 组件系统协议常量（统一 magic string） |
| `errors.py` | 统一异常层级 |
| `debug_report.py` | 失败现场报告工具（parser/linter 共用） |
| `global_state.py` | 引擎全局状态快照/还原（测试隔离，顺序无关） |
| `_user_config.py` / `utils.py` | 用户项目配置定位 / 通用工具 |

> 配置机制见 `core/config_lifecycle.md`；组件协议见 `core/component_protocol.md`。
> 配置错误一律 fail-fast（core/config_lifecycle.md），不静默降级。
