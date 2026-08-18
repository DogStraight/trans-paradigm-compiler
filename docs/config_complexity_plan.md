# 配置复杂度管理计划

> 日期：2026-08-18
> 背景：Jeff Dean 视角审视——配置加载/生命周期反直觉（P2.0 技术债）；调研 LLVM
> TableGen / PostgreSQL GUC 等知名项目的配置管理方式，提炼可借鉴机制。
> 目标：让配置机制"可观测、可校验、可调试"，服务"模型可代写"设计基准。
> 状态：✅ 步骤 1-5 全部完成（2026-08-18，685 测试全过）

---

## 调研结论（知名项目如何管理配置复杂度）

### LLVM TableGen（最相关：声明式配置驱动编译器）

- 配置是**编译期 DSL**（class/def/multiclass/foreach/let），有类型系统，编译成
  C++ `.inc` 文件，不是运行时解释
- 每个消费方是一个 **backend**，把 records 解释成特定输出（CodeEmitter/RegisterInfo/...）
- 有**调试工具**：`-print-records` / `-print-detailed-records` / `-dump-json`
- 官方自认缺陷（TableGen Deficiencies）：DSL 表达力不足 → 文件膨胀；自定义 backend
  可 pervert 原设计，让新人难以理解

### PostgreSQL GUC（运行时配置生命周期）

- 明确的**来源优先级链**：编译期默认 < `postgresql.conf` < `postgresql.auto.conf`
  (ALTER SYSTEM) < 命令行 `-c` < ALTER DATABASE/ROLE < 会话级 SET
- 明确的**加载时机 + context 分类**：启动读 conf、SIGHUP 重载；每个参数有 context
  （postmaster/sighup/backend/superuser/user）决定何时可改
- **可观测性**：`pg_settings` 视图（name/context/unit/setting/reset_val/enumvals）、
  `pg_file_settings`（预测试）、`SHOW`/`SET`
- **模块化**：`include` / `include_if_exists` / `include_dir`，命名约定（`00shared.conf`）
  保证加载顺序
- **校验**：无效设置在 SIGHUP 时被忽略但记录日志

### 对照 tpc

| 机制 | 来源 | tpc 现状 | 借鉴价值 |
|------|------|---------|---------|
| 配置 schema + 校验 | TableGen class / K8s CRD | `_KNOWN_FIELDS` 白名单，校验零散 | 高——服务模型可代写 |
| 配置来源可观测 | PG pg_settings | 无 | 高——解决"值从哪来" |
| 配置优先级显式化 | PG 来源链 | 隐式 | 中——文档化 |
| 配置调试工具 | TableGen print-records | 无 | 高——`tpc config dump` |
| 配置编译期生成 | TableGen | 运行时解释（TOML） | 不借鉴——运行时解释是优势（改配置不重编译） |
| 配置模块化/分层 | PG include_dir | 已有（`0x_` 前缀 glob 排序） | 保持 + 文档化加载顺序 |

## 核心判断

tpc 配置机制已比 TableGen 更"模型友好"（TOML 运行时解释 vs 编译期 DSL），缺的是
三样——这三样恰好是"模型可代写"成立的关键（模型写配置时能拿到校验反馈和调试信息）：

1. **配置 schema 校验**：模型写配置时能拿到结构化错误
2. **配置来源可观测**：值从哪个文件+section 来
3. **配置调试工具**：`tpc config dump`

## 计划步骤

### 步骤 1：配置来源追踪（ConfigRegistry）— P0 ✅ 完成
- 目标：记录每个配置 key 的值来源（实际文件 + section）
- 改动：`core/config_registry.py`
  - `_resolve_decls` 返回 `(loaded, sources)`
  - `load_all` 存 `cls._sources`
  - `resolve` 缓存 `(loaded, sources)`，新增 `resolve_with_sources`
- 验证：单测 + 全量测试

### 步骤 2：`tpc config dump` 调试命令 — P0 ✅ 完成
- 目标：输出所有配置 key 的当前值 + 来源层级
- 改动：`main.py` + 测试
- 验证：CLI 手动 + 单测

### 步骤 3：配置声明结构校验（schema 化第一步）— P1 ✅ 完成
- 目标：校验 tpc.toml 声明结构（file/section/required 字段合法性），fail-fast
- 改动：`core/config_registry.py` `_load_meta_declarations`
- 验证：单测（坏声明报错）

### 步骤 4：规则字段 schema 化 — P1 ✅ 完成
- 目标：为 GrammarRule 字段定义 schema（合法字段、类型、必填），加载时统一校验
- 改动：`core/define.py` + grammar 校验
- 验证：单测 + 全量

### 步骤 5：配置生命周期文档更新 — P2 ✅ 完成
- 目标：把三阶段时序 + 新机制（resolve/来源追踪/dump）更新到 `config_lifecycle.md`
- 改动：`docs/config_lifecycle.md`

## 优先级

- **P0**：步骤 1-2（来源可观测 + 调试工具）——直接解决"值从哪来"痛点
- **P1**：步骤 3-4（schema 校验）——服务模型可代写
- **P2**：步骤 5（文档）

## 关联

- 本次 Lexer 配置 bug（值不跟随语言包）根因即"配置来源不可见"——来源追踪后此类
  问题可快速定位
- 已实施的 `resolve()` 依赖注入（2026-08-18）是配置生命周期简化的正确方向，可推广
