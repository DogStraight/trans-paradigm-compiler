# 配置生命周期（declare_cfg 注册制）

> 文档目的：解释 `declare_cfg` 注册制配置的三阶段时序，以及由此产生的常见怪象
> 与规避方式。来源：2026-08-12 c4 第二语言过程踩了 3 个修复（walkthrough #1/#2/#3）。

## 三阶段时序

```
阶段 1：import 期注册       阶段 2：load_all 推送        阶段 3：运行读取
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
│ 模块 import 时执行    │   │ 管线启动点调用        │   │ 代码通过模块级    │
│ declare_cfg(key,     │   │ ConfigRegistry.      │   │ 变量使用真实值    │
│   default, __name__) │   │ load_all(rules_dir)  │   │ （_xxx_cfg）      │
│ → 注册到             │   │ → 解析 tpc.toml      │   │                  │
│   _CONFIG_DECLARATIONS│   │ → _push_loaded_config│   │                  │
│ → 模块变量 = 默认值   │   │ → 模块变量 = 真实值  │   │                  │
└──────────────────────┘   └──────────────────────┘   └──────────────────┘
```

**关键事实**：

1. `declare_cfg(key, default)` 在**模块 import 时**注册并返回默认值。
2. `load_all(rules_dir)` 完成后，`_push_loaded_config` 把真实值**推入所有已 import 模块的模块级变量**。
3. **必须在 `load_all` 之前 import 全部消费模块**——否则该模块的 `declare_cfg` 注册晚于推送，变量永远是默认值。

## 常见怪象

### 怪象 1：必须先 import 全部模块再 load_all

```
错误：
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all("grammar/verilog")   # 先 load
    from lexer import Lexer                       # 后 import
    # Lexer 的 _token_base_cfg 注册晚于推送 → 持有默认值 {}，token 全退化

正确：
    from lexer import Lexer                       # 先 import（注册全部 declare_cfg）
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all("grammar/verilog")   # 后 load（推送真实值）
```

### 怪象 2：换语言后新 import 拿到旧默认值

```
ConfigRegistry.load_language("grammar/c4")   # 换语言
from parser import SomeModule                # 新 import
# SomeModule 的 declare_cfg 在 load_language 之后注册
# → _resolved=True，declare_cfg 直接返回 _loaded 当前值（c4 的）
# → 之后切回 verilog，SomeModule 仍持有 c4 值（注册未重推）
```

**规避**：换语言后如需新模块，用 `load_language` 后再次 `_push_loaded_config`，
或保持"全部模块在启动时一次 import"。

### 怪象 3：改 tpc.toml 后进程内不生效

```
ConfigRegistry.load_all 有缓存（_PIPELINE_SHARED / _loaded）
→ 同进程内改 tpc.toml 不会重载
→ 需新进程 / 显式 reload
```

## 为什么用注册制

- 消费模块**声明式**列出自己的配置依赖（key + 默认值），不感知加载细节。
- `get_config_refs()` 从 `_CONFIG_DECLARATIONS` 查询，避免源码扫描。
- 支持**多模块共享同一 key**（每个声明者都收到推送）。

## 最佳实践

1. **启动时一次性 import 全部消费模块**（run_pipeline.py 顶部 import 就是这么做的）。
2. 消费模块只通过**模块级变量**（`_xxx_cfg`）读配置，不直接调 `ConfigRegistry.get`。
3. 新增消费模块：在文件顶部 `_xxx_cfg = declare_cfg(...)`，确保它在 load_all 前被 import。
4. 测试中改配置：monkeypatch 模块级变量（不依赖 ConfigRegistry 重载）。

## 评估结论（2026-08-13）

- **保持注册制**（不改成显式 config 对象注入）——机制已工作，改动成本高、收益有限。
- 本文档作为"配置生命周期"权威说明；walkthrough 补一节引用本文档。
- 已知风险点：import 时序依赖（怪象 1）——用"启动点统一 import"惯例约束，文档化即可。
