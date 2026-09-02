# ADR-0012: 多后端输出设计（P4.1 蓝图，后端 = 同构渲染器实例）

- Status: draft（设计定稿未实现；P4 立项后升 accepted）
- Date: 2026-08-28（定稿）；2026-09-02（自 docs/references.md 迁入）
- Supersedes: references.md 同章节（内容迁移，非推翻）

## 背景

当前渲染器体系"一套配置一套输出"——transform 串行覆盖主 AST
（`ast = plugin.process(ast)` 链式，第一个后端插件产出 AsmProgram 后，
第二个后端插件看到的已非源 AST）；布局是单一命名空间（load_layouts 按
节点名合并）；mark_extra 只能从已变换 AST 取子树，不能从源 AST 独立变换。

## 决策（定稿方案）

**后端 = 同构渲染器实例**（用户设计，比旁路插件+mark_extra 更彻底）——
插件系统实例化特定后端的渲染器，与主管线渲染器**同一个 Renderer 类**
（零引擎分裂，仅布局配置不同）；语言配置留在插件目录；主管线渲染器只
负责主 AST 原样打印。

### 现状支撑（已验证）

- Renderer 已是可实例化类（`Renderer(rules_dir)` → load_layouts → render，
  零语言特定代码）。
- load_layouts 递归 rules_dir 含 plugins/ 子目录（插件布局声明机制已存在，
  缺"作用域"）。
- mark_extra/collect_extra_asts 多文件输出雏形已有。

### 引擎补丁 3 处

1. `Renderer.__init__` 加 `layout_dirs` 参数（插件级布局目录后加载）
2. plugin_loader 识别旁路后端插件（tpc.toml `[transform] target = "llvm"`）
   → 实例化同构渲染器（布局=插件目录）
3. 旁路插件 process 基于**源 AST**（transform 前干净形态）→ 产物节点交
   自己的渲染器 → 独立文件输出（复用 mark_extra 通道）

### 配置不复杂保证

复杂度 = O(插件数)——主管线零改动（无旁路插件时行为与现状一致）；新增
后端 = 一个自包含插件目录（transform handler + 布局声明 + target），不给
主规则配后端布局；后端节点族节点名与主 AST 不重叠（AsmProgram/
LLVMProgram 等），布局命名空间天然隔离。

### 待拍板

旁路后端默认全部输出（零配置）vs 引入 `--backend` 选择参数——倾向先
全部输出，按需选择等真实需求再加。

## 权衡

- 被拒绝备选：旁路插件 + mark_extra（从已变换 AST 取子树，不能从源 AST
  独立变换——表达不了"同一源文件多种目标输出"）。
- 收益：零引擎分裂（复用 Renderer 类），新增后端 = 纯插件目录，主管线
  无旁路插件时行为不变（向后兼容免费）。

## 验证

- draft：无实现验证。P4 立项后以本文为设计起点；验收 = 新增一个后端
  插件（如 LLVM IR 目标）走通"源 AST → 独立渲染 → 独立文件"，主管线
  输出不变（全量回归）。

> Impl: 待实现（P4 立项后；Renderer.layout_dirs + plugin_loader target 识别）
> Test: 待实现（P4 立项后）
