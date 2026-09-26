# 发布 SOP（release checklist）

> 每次发布走一遍。0.1.0 = Alpha（classifier "3 - Alpha"）；发布定义见 TODO P2.2。
> 发布基线 = "主包纯净可综合"（可综合子集进主包 + 仿真进 plugins/sim）。

## 0. 发布前置（git 侧）

- [ ] 工作区干净：`git status --short` 无未提交/未跟踪改动（临时脚本除外）
- [ ] CHANGELOG 已归拢：`[0.1.0] - YYYY-MM-DD` 段含首版条目（首版后：Unreleased → 新版本段）
- [ ] TODO 发布收尾项全部勾选（P2.2 硬缺口）
- [ ] `docs/gaps/` 未闭环项复核：是否仍成立 / 已被实现——**已实现直接删条目**
      （不写"已修复"注记）；方案细节与代码不符的删细节只留方向

## 1. 回归门禁（发布前必须全绿）

```bash
python -m pytest tests/ -q                      # 单测全绿（默认并发）
python tests/e2e/run_all_tests.py               # e2e FAIL 0
python tests/e2e/eval_lint_accuracy.py          # lint recall 100%、误报 FP 0
python -m pytest tests/ -q --cov --cov-report=term # 覆盖率 ≥ fail_under（80；并行即准，无需 -n 0）
```

> 或**一条命令**跑完 CI 的全部步骤（含 pyright strict / edge / fuzz / wheel 安装冒烟）：
> `python tools/ci_rehearsal.py`。结论三态 **PASS / FAIL / INCOMPLETE**——
> **SKIP（本机缺 pyright 等）与「一步都没跑」都不算绿**，整体判 INCOMPLETE 并 exit 2。
> ⚠ CI 的触发是 `push.branches` + `pull_request`，**推 tag 不触发 CI**；长期不推送期间
> 门禁等于没跑（已实测累积 4 类红，见 `TODO.md`「测试基础设施」）——**打标前必须先跑本工具**。

## 2. 版本号核对

- [ ] 版本单一来源 `core/__init__.__version__` 与 `pyproject.toml [project].version` 一致
      （`tests/engine/core/test_version.py` 锁定；改版本时两处同步改 + 改测试期望？——不，
      测试断言两者相等，只需同步改两处）
- [ ] `tpc --version` 输出正确版本

## 3. 构建 sdist / wheel

```bash
python -m build            # 需 pip install build；产出 dist/trans_paradigm_compiler-<version>.tar.gz + .whl
```

## 4. 验证包内容（不扁平化）

```bash
python -m zipfile -l dist/*.whl | Select-String 'grammar/'
# 必须保留（顶层按语言包分目录；实测随包：verilog / c / c4 / yaml）：
#   grammar/verilog/tpc.toml + 各规则 TOML + plugins/（typed_ports/formatter/checks/...）
#   grammar/c/tpc.toml + 规则 TOML + base/ + plugins/{c11,c17,c23}/（标准增量插件）
#   grammar/c4/tpc.toml + 规则 TOML + plugins/
#   grammar/yaml/
# 不要出现 data-files 扁平化（各语言包混在一起 = 失败）
tar -tf dist/*.tar.gz | Select-String 'grammar/'   # sdist 同样核对
```

> 各包 TOML **逐个**核对，别只看"有 grammar/ 目录"：新增语言包漏进包（`package-data`
> 未覆盖）在 wheel 里表现为静默缺失，而我们默认语言仍是 verilog ⇒ 冒烟（下节）**跑不到**
> 非默认包。C 包 0.1.3 实测 = 19 个 TOML（与源码树逐一对上），机制为
> `[tool.setuptools.package-data] "grammar" = ["**/*.toml"]` 递归匹配。
> **非 TOML / 非 `.py` 的文件不随包**（包内 `README.md`、`cases/*.sv` 用例样本、
> `__pycache__`）——0.1.3 实测 verilog 磁盘 181 → wheel 114，差异**全是这两类**：
> 包内文档与用例样本只服务仓库内测试，别指望它们出现在 wheel 里。
> CLI 侧的语言选择开关仍在 ROADMAP「用户侧 CLI 形态」（触发式 backlog），
> 故非默认包目前只做清单核对。

## 5. wheel 冒烟（独立 venv，模拟用户安装）

```powershell
py -3.11 -m venv .venv-smoke
.venv-smoke\Scripts\pip install dist\*.whl
.venv-smoke\Scripts\tpc --version
.venv-smoke\Scripts\tpc format tests\e2e\samples\normal\ref\ref_alu.v   # 无报错
.venv-smoke\Scripts\tpc lint tests\e2e\samples\lint_err\ref\ref_e01_missing_endmodule.v  # exit 1
.venv-smoke\Scripts\tpc lint tests\e2e\samples\normal\ref\ref_alu.v     # exit 0
.venv-smoke\Scripts\tpc check tests\e2e\samples\normal\ref\ref_alu.v    # exit 0 / No issues found
# 再从任意目录（如 %TEMP%）跑一条，验 rules_dir 解析到 site-packages 内 grammar 包
Remove-Item -Recurse .venv-smoke
```

> wheel 安装后从任意目录运行：rules_dir 相对路径解析到 site-packages 内
> grammar 包（pipeline 已处理），不依赖项目 CWD。

## 6. 打 tag + 发布

```bash
git tag -a v0.1.0 -m "0.1.0 Alpha — configuration-driven language pipeline"
git push origin v0.1.0
```

## 7. PyPI 上传（可选）

```bash
python -m twine check dist/*
python -m twine upload dist/*   # 需 PyPI 凭证（__token__）
```

## 8. 发布后

- [ ] CHANGELOG 顶部开新 `## [Unreleased]` 段
- [ ] 更新 docs/README.md / MODEL_INDEX（若新增知识单元）
- [ ] 通知/记录（CHANGELOG 首版条目已含基线：pytest 数 / e2e 数 / lint recall）
