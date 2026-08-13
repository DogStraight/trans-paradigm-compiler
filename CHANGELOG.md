# Changelog

所有重要变更按时间倒序记录。版本格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### 2026-08-13（P2 工程化收尾）

- 文档化 P2.0 四项：config_lifecycle / expression_conventions / component_protocol /
  c4 最小语言包模板定位
- 安装验证：`pip install -e ".[test]"` + CLI 实测工作
- 覆盖率门禁：.coveragerc（omit 入口/回退，fail_under=84，实测 84.57%）
- 恢复 CI：.github/workflows/ci.yml（Windows + Python 3.11/3.12/3.13）
- 修复：linter `to_dict` 缩进死代码 → `lsp_diagnostic`（--json 必崩 bug）
- 删除死代码 core/component_loader.py（被 plugin_loader 取代）

### 2026-08-13（P1 完成）

- formatter：宽度折行 pass（wrap）、SV 基础覆盖（logic/always_ff/always_comb）、
  风格参数化（formatter.style）
- 预处理器 primitives 级单测 19 项
- 增强渲染验证补充（nested/invert + TypeNestedPort layout）
- 数字形态配置化：声明→FSM 生成器 + 语言包声明 + signed `'s` + `0'b1` 标准拒绝

### 2026-08-12（P0 第二语言）

- c4 完整实现（.c → c4 VM 汇编），6 集成测试——语言无关主张实证
- P0.3 渗透清理：boundary 语言渗透消除（ScopeKind 规则推导）
- 修复 7 个核心渗透/单语言假设（详见 docs/language_walkthrough.md §7）

## [0.1.0]

- 初始版本：Verilog 语言包 + 完整管线（lex/parse/analyze/transform/render/lint）
- formatter 插件（品类对齐/缩进/ifdef/幂等）
- typed_ports 增强语法（类型端口/impl 绑定/自动连线）
- 预处理器（宏展开/条件编译还原）
