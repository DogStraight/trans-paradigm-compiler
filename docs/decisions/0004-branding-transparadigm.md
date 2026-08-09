# ADR-0004: 品牌命名 TransParadigm（CLI: tpc）

- Status: accepted
- Date: 2026-08-10

## 背景

原品牌 `pyv`（Py + Verilog）存在三层问题：
1. **不表达核心**：项目核心是"范式 → 范式"的配置驱动语言映射（transpile/elaborate），而非"Python + Verilog"。
2. **语义家族淹没**：`pyv-` 前缀在 Python 生态泛滥（pyvista/pyvisa/pyvmomi/pyvis…），且同域有先行者 Pyverilog（Python-Verilog 工具，797★），`pyv` 零辨识度。
3. **注册 vs 品牌分层不清**：`pyv` / `pyv-compiler` 在 PyPI 均 404 可注册——问题在品牌/语义层，不在注册层。

## 决策

- **品牌**：TransParadigm（包名 `transparadigm-compiler`）
- **CLI**：`tpc`（console script `tpc = main:main`）
- **语义**：trans（转换，拉丁词根，覆盖"范式→范式"不绑定终点）+ paradigm（范式）——表达"把任意范式映射/转换为另一种范式"。
- **保留不动**：配置文件 `pyv.toml` / `pyv_config.json` 文件名及加载字符串、环境变量 `PYV_CONFIG` / `_PYV_STAGES`、测试生成物快照、`references.md` 历史引用。

## 权衡 / 命名方法论（可复用）

1. **模型无法产出低概率名**：LLM 从概率分布采样，必然输出人类也高频想到的词（mint/forge/pts…全被占）。独特名靠**长组合词 + 穷举 + 核查**，不靠模型生成。
2. **X2Y 缩写被否**：E2S/P2T/C2T 等绑定"到目标语言"，与"范式→范式"能力不符；且三字母缩写必然撞名（s2t=语音、ppt=PowerPoint、p2p=点对点）。
3. **长组合词占位空间大**：`transparadigm`（13 字母）代码层零占用（PyPI 404、GitHub total 0），比短缩写干净一个量级。
4. **品牌固定 + 语法资产按语言后缀**：引擎名固定（`tpc`），语法资产（`grammar/<lang>/`）动态——与 ADR"语法资产独立可发布"自洽。
5. **命名核查流程**：候选 → PyPI JSON API + GitHub search API 占位核查 → 过滤 → 定稿。避免"凭印象说冲突少"。

## 验证

- 占位：`transparadigm`/`trans-paradigm` PyPI 404、GitHub 0 仓库；`tpc` PyPI 404、GitHub 无精确同名。
- 改名后：`tpc` CLI 可用、`tpc format` 端到端正常、pytest 329 全绿（linter source 改 `tpc-lint` 无破坏）。

> Impl: pyproject.toml（name + [project.scripts] tpc）
> Impl: main.py（CLI description / 子命令 docstring）
> Impl: linter/__init__.py（source: "tpc-lint"）
