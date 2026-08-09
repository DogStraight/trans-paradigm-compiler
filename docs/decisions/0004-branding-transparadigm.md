# ADR-0004: 品牌 TransParadigm（CLI: tpc）

- Status: accepted
- Date: 2026-08-10

## 决策

- **品牌**：TransParadigm（包名 `transparadigm-compiler`）
- **CLI**：`tpc`（console script `tpc = main:main`）——Trans-Paradigm-Compiler 首字母；全名 13 字母太长，CLI 取短名，可念且占位干净（PyPI 404、GitHub 无精确同名）。
- **语义**：trans（转换，拉丁词根，覆盖"范式→范式"不绑定终点）+ paradigm（范式）——表达"把任意范式映射/转换为另一种范式"。
- **早期名称占位**：`pyv` 为本项目早期品牌名（Py + Verilog），已全部迁移——`pyv.toml`→`tpc.toml`、`pyv_config.json`→`tpc_config.json`、`PYV_CONFIG`→`TPC_CONFIG`、`_PYV_STAGES` 移除（无读取者）。

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
