# 配置生命周期（declare_cfg 注册制）

> 文档目的：解释 `declare_cfg` 注册制配置的三阶段时序，以及由此产生的常见怪象
> 与规避方式。来源：2026-08-12 c4 第二语言过程踩了 3 个修复（walkthrough #1/#2/#3）。

## fail-fast（配置损坏不静默降级）

配置加载对损坏**不静默降级**（原 ADR-0003 决策，2026-09-08 归档迁入）：
`TOMLDecodeError` / 缺声明 section / 非"文件缺失"异常一律 fail-fast 报错
（仅 `FileNotFoundError` + required=False 容忍）；token define 有结构自检
（`lexer_utils._validate_token_define` 关键段存在校验）。动机：2026-07-26
token.toml 重复 key 事故——解析失败被 `except` 当"可选缺失"静默存空表 → token
全退化为 id → linter 全面崩溃。**静默错乱是"假绿"温床**——配置损坏在入口暴露，
不运行期难查。实现见 `config_registry.py::ConfigRegistry.load_all` 异常分类。

## 包↔引擎契约：`[engine] uses` 能力清单（2026-09-25）

`grammar/<lang>/tpc.toml` 可声明：

```toml
[engine]
uses = ["lexer.token_ext.v1", "parser.pratt.v1"]
```

语义：逐项列出该包**依赖的引擎契约面**（能力表与版本语义见
`core/engine_capabilities.py`）。每项须是引擎已知能力且版本匹配，否则**拒绝加载**
（`ConfigError`，fail-fast），报错**点名是哪一项能力**（包的版本 vs 引擎的版本）。
**未声明 = 不校验**（纯增量：ad-hoc 包与测试夹具不受影响）。

**为什么不是"整条 API 线"**（原 `api = "0.1"`，已于本版删除）：整条线的粒度让
①引擎 minor 一动**所有**包都被拦（哪怕该包只用语法声明、没碰精化协议），
②报错说不出**缺哪一项**。能力协商把受影响面收敛到"**声明了该能力**的包"，
报错直接指出迁移对象；引擎内部重构/优化/文案调整**不**升版本（判据见能力表头注，
否则受影响面会被自己放大成常态）。

**单一来源纪律**：`uses` 不许凭记忆写——`required_capabilities()` 从包**自己的清单**
（tpc.toml 段 + `[capabilities]` 键 + `rules/*.toml`）机械推导，门禁
`tests/policy/test_engine_capabilities.py` 断言"推导集 ⊆ 声明集"（漏声明即红）
与"声明集 ⊆ 能力表"（改名/删除的残留即红）。

**不留向后兼容**：`[engine]` 只认 `uses` 一个键——残留的 `api = "0.1"` 会被"未知键"
在加载期拦下（响亮失败，不静默忽略）。

校验点两处（不同入口，都不可省）：`_load_meta_declarations`（`load_all` /
`resolve` 路径）与 `core/define.py::_load_tpc_meta`（import 期默认包）。
`[engine]` **不是配置声明**——注册时跳过（否则会被当 bare data 进配置中心）。
契约实现见 `core/engine_compat.py` + `core/engine_capabilities.py`，回归
`tests/engine/core/test_engine_compat.py`（协商语义）+ `tests/policy/test_engine_capabilities.py`
（覆盖不变式）。

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

## 语言包参数化（2026-08-18 更新）

`load_all(rules_dir)` 现在**自动按语言包切换声明**：若 `rules_dir` 存在
tpc.toml 且与当前声明来源（`_entries_source`）不一致，先按该语言包 tpc.toml
重新生成声明再加载——glob 匹配/文件路径声明都基于当前语言包，而非 import
期锁定的默认包。因此：

```python
# 无需先 load_language——直接 load_all(c4 目录) 即切换到 c4 语言包
ConfigRegistry.load_all("grammar/c4")

# 切回 verilog（插件声明需要 plugins_dir）
ConfigRegistry.load_all("grammar/verilog", plugins_dir="grammar/verilog/plugins")
```

例外：rules_dir 无 tpc.toml（临时目录等低层用法）时保持现有声明不变，
load_all 只换 base 目录（兼容直接 `declare` + `load_all` 的契约）。
`load_language` 保留（显式单语言选择 API），内部与 `load_all` 共用同一
`_ensure_entries_for` 逻辑。

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

## 2026-08-18 更新：配置复杂度管理（来源可观测 + 校验 + 调试）

### 1. 按语言包自包含解析（resolve，无全局副作用）

`ConfigRegistry.resolve(rules_dir, ...)` 按指定语言包解析配置，**不写 _loaded、
不改 _entries、不推模块变量**——纯函数语义，按参数缓存。

```python
# Lexer 按自己的 rules_dir 解析，不依赖最后一次 load_all 的全局状态
resolved = ConfigRegistry.resolve("grammar/c4", plugins_dir="grammar/c4/plugins")
```

**动机**：Lexer 配置（token/数字形态）曾依赖"最后一次 load_all 的语言"——同一进程
跨语言时串用上一语言配置（c4 的 `0x1F` 被拆成 `0`+`x1F`、`int` 被当 id）。resolve
让消费方按语言包自包含解析，彻底摆脱隐式全局状态。

**消费方**：`Lexer.__init__`（rules_dir 分支）一次 resolve 取 token/宏/数字形态。

### 2. 配置来源追踪（_sources / resolve_with_sources）

`load_all` 后 `ConfigRegistry._sources` 记录每个 key 的实际来源：

```python
ConfigRegistry._sources["lexer.number"]
# → {"file": "grammar/verilog/base/_number.toml", "section": "number"}
#   {"bare": True} 裸配置 / {"missing": True} 可选缺失
```

`resolve_with_sources(rules_dir, ...)` 返回 `(loaded, sources)` 对（无全局副作用）。

**动机**：回答"这个配置值从哪来"——本次 Lexer 配置 bug 根因即来源不可见。

### 3. `tpc config dump` 调试命令

```bash
python main.py config dump                 # 文本：key + 来源 + 值摘要
python main.py config dump --rules-dir grammar/c4
python main.py config dump --json          # JSON（ensure_ascii，Windows 兼容）
```

输出每个配置 key 的来源（文件 + section）与值摘要，服务模型/人调试。

### 4. 配置声明结构校验（schema 化第一步）

`_load_meta_declarations` 解析 tpc.toml 时校验声明结构（fail-fast）：

- 文件式声明：`file` 必须 str/list[str]，`section` str/None，`required` bool，
  `base` str，无未知字段
- dict 含声明字段但缺 `file`（如 `{ section = "x" }`）→ 拦截（疑似忘了 file）
- 合法 bare data（非 dict，或纯数据 dict）通过

### 5. 规则字段 schema 校验（GrammarRule）

`GrammarRule._validate_fields` 在构造时校验（fail-fast）：

- **顶层字段**严格：`_KNOWN_FIELDS | {inject, transform, parser, analyzer, renderer}`
- **parser/renderer 阶段**严格：parser 含 `scope`（`_resolve_peek` 拷贝产物）
- **analyzer 阶段宽松**：scope/symbol/ref_collect/identifier_ref/primitives 是引擎
  字段，其余是插件原语名（开放扩展点，如 check_name_call）
- **布尔字段**类型校验（is_statement/is_atom/inline/pratt/is_block）

**附带修复**：`FileManager.load_all_toml` 跳过 `tpc.toml`——其 `[lexer]`/`[parser]`
等段是配置声明，此前被静默当规则加载（schema 校验后暴露）。

### 6. 配置优先级链（现状，供参考）

```
编译期默认（declare_cfg default） < 语言包 tpc.toml 声明 < 用户 tpc_config.json
< CLI 参数（main.py 指令覆盖）
```

用户 tpc_config.json 的**定位顺序**（core/_user_config.py）：

```
$TPC_CONFIG env（显式） > CWD 向上 config/tpc_config.json（工作区隔离）
> ~/.tpc/config.json（全局 profile，一次配置任意工作区享用） > 内建默认
```

与 PostgreSQL GUC 的"来源优先级链"同构，但 tpc 的覆盖点更少（无会话级/角色级）。
如需显式化，可扩展 `tpc config dump` 输出优先级层级。
