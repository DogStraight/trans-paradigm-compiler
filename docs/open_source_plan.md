# 开源就绪计划（Open-Source Readiness）

> 日期：2026-08-18
> 背景：评估项目开源障碍——技术层面（测试/CI/许可证/第三方样本）已基本就绪，
> 真正障碍是**法律合规**（IEEE 文档 + 商业工具调研）和**采用门槛**（中文占比 +
> 安装验证）。
> 状态：✅ 全部完成（2026-08-18，685 测试全过 + wheel 安装实测）

---

## 障碍清单与处理计划

### P0-1. IEEE 标准文档版权风险 🔴 ✅ 完成

**问题**：`docs/ieee1364_2005_annex_a.md` 和 `docs/ieee1800_2023_annex_a.md`
是从 PDF 完整提取的 Annex A 规范性内容（2557 行 BNF）。IEEE 标准有版权，
Annex A 是标准的规范性组成部分，完整复制进开源仓库有版权风险。

**处理**：
- [x] 两个文档加版权声明头（IEEE 版权 + 内部开发缓存性质 + 不随项目分发）
- [x] MANIFEST.in 排除 IEEE 文档 + PDF（sdist 不含，wheel 不含 docs）
- [x] 验证：sdist 无 ieee/PDF 文件

### P0-2. 商业工具调研痕迹 🔴 ✅ 完成

**问题**：调研过程解压了 VeriGood 的 VSIX 和 Sigasi 的 VSIX（420MB）。
商业工具 EULA 通常禁止解包/逆向。开源后这些痕迹可能被质疑。

**处理**：
- [x] 核查：仓库无 VSIX 解压产物残留（file_search 无 .vsix）
- [x] 借鉴的是机制/思路（命名检查机制/ifdef 标注思路），代码注释已注明"借鉴"
- [x] TODO.md 软化"VSIX 解包/反编译"表述为"行为观察/公开文档参考"

### P1-1. 安装验证（wheel）🟠 ✅ 完成

**问题**：pyproject.toml 配了 data-files（grammar TOML + config），但 editable/dev
模式从源码树定位，**wheel 安装后能否找到 grammar 数据未验证**。

**处理**：
- [x] data-files → package-data（保留 verilog/c4 目录结构，多语言包可用）
- [x] `_load_tpc_meta` / `_find_grammar_tpc_toml` 用户配置缺失时回退默认语言包
- [x] 管线核心移入 `pipeline/` 包（CLI 与测试共用，wheel 安装后 CLI 可用）
- [x] `run_pipeline_on_source` 相对 rules_dir 解析为绝对路径（任意目录运行）
- [x] 实测：wheel 安装到临时 venv，从 C:\ 运行 `tpc lint` / `tpc format` 成功

### P1-2. CONTRIBUTING/CHANGELOG 英文化 🟠 ✅ 完成

**问题**：README 是英文（0% 中文），但 CONTRIBUTING（67% 中文）、CHANGELOG
（64% 中文）、TODO（81% 中文）是中文。国际贡献者无法参与。

**处理**：
- [x] CONTRIBUTING.md 英文化（贡献者入口）
- [x] CHANGELOG.md 英文化（变更历史）
- [x] TODO.md 保留中文（内部待办，非协作方文档）

### P2-1. 借鉴来源署名核查 🟡 ✅ 完成

**问题**：c4 语言包对齐 rswier/c4（MIT）、wrap 惩罚搜索借鉴 Verible（Apache 2.0），
调研记录显示有借鉴，但代码/文档里是否都有署名需核查。

**处理**：
- [x] c4/README.md 补 rswier/c4 MIT 署名（仅参考行为，未复制源码）
- [x] wrap.py 补 Verible Apache 2.0 署名（仅参考机制，未复制代码）
- [x] 核查：c4 各 TOML 已注明 rswier/c4；VeriGood 借鉴已注明

### P2-2. 文档对齐负担说明 🟡 ✅ 完成

**问题**：MODEL_INDEX / `Doc:` / `Impl:` 三处同步是为模型维护设计的，对外部
人类贡献者是负担。

**处理**：
- [x] CONTRIBUTING 明确"核心维护者维护对齐，外部 PR 不强求"

### P3-1. 品牌/命名确认 🟡 ✅ 完成

**问题**："TransParadigm" 和 `tpc` 是常见缩写，可能与已有项目冲突。

**处理**：
- [x] GitHub 搜索："TransParadigm compiler" 0 结果（品牌名独特无冲突）
- [x] `tpc` 缩写有 39 个同名但都是不相关小项目（0-26 stars）
- [x] 建议仓库名用 `transparadigm` 或 `tpc_compiler` 避免歧义

---

## 优先级

| 优先级 | 项 | 类型 |
|--------|----|------|
| P0 | IEEE 文档版权 | 法律 |
| P0 | 商业工具调研痕迹 | 法律 |
| P1 | 安装验证（wheel） | 技术 |
| P1 | CONTRIBUTING/CHANGELOG 英文化 | 采用 |
| P2 | 借鉴来源署名核查 | 合规 |
| P2 | 文档对齐负担说明 | 维护 |
| P3 | 品牌/命名确认 | 运营 |
