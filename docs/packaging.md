# 功能切面打包管线（单一文件可执行）

> 用途：把需要的**功能切面**（format / lint / expand / config...）打包成单一
> 文件 exe——内置 Python 运行时 + 全部引擎代码 + Verilog 语法包，不装 Python、
> 不装包、不依赖项目树即可运行。对标 clang-format / prettier 的单二进制分发，
> 但按切面裁剪：**一个 exe 只带你要的命令**。

## 管线

```
packaging/facets.json（切面规格）
        ↓
packaging/build_pipeline.py（生成入口 → Nuitka onefile → SHA256）
        ↓
dist/<name>.exe + dist/SHA256SUMS.txt
```

```powershell
pip install nuitka          # 构建期依赖；运行时零第三方依赖不变
python packaging/build_pipeline.py tpc-fmt     # 构建单个切面
python packaging/build_pipeline.py --all       # 构建 facets.json 全部
python packaging/build_pipeline.py tpc-fmt --dry-run   # 只生成入口不构建
```

## 切面规格（packaging/facets.json）

```json
{
  "tpc-fmt":  { "facets": ["format"], "file_description": "...", "product_name": "..." },
  "tpc-lint": { "facets": ["lint"],   "...": "..." },
  "tpc":      { "facets": ["format", "lint", "expand", "config"], "...": "..." }
}
```

- `facets` = 命令名集合（对应 `main._register_subparsers(sub, allow)` 的裁剪；
  生成入口只挂载这些命令，**未选中的命令不存在**）。
- 新增切面：在 facets.json 加一个条目即可，管线自动生成入口并打包。
- 行为一致性：入口复用 `main._dispatch`，与 `tpc <cmd>` 完全一致，无行为漂移。

## 打包器：Nuitka（为什么不是 PyInstaller）

PyInstaller 的 bootloader 自解压特征容易触发杀软启发式误报；Nuitka 编译成真
C 代码，误报率显著更低。本机验证 MSVC Build Tools 14.44。

> 诚实边界：**未签名 exe 从网上下载后 SmartScreen 仍会警告**——Windows 平台
> 策略，Nuitka/PyInstaller 都绕不开，**代码签名是唯一根治**（OV/EV 证书，
> 发布时考虑）。Nuitka 解决的是杀软启发式误报，不是 SmartScreen。

## 署名（透明 + 可溯源，三层）

被逆向/被怀疑时，对方应当能定位作者与来源：

1. **PE 版本资源（未压缩，零逆向可见）**：CompanyName/描述/版权（含邮箱与
   仓库 URL）。**`strings -el <exe>` 直接扫出**（PE 资源是 UTF-16）。
2. **二进制内嵌标记（压缩载荷内）**：入口脚本烘焙的 CREDITS_TEXT——逆向解包
   后 `strings` 可查。
3. **`--credits` 命令**：零逆向成本直接打印。

```
tpc-fmt 0.1.0 — TransParadigm Verilog toolchain
Author: biominescence <oho15799293498@outlook.com>
AI Co-author: deepseek-v4-flash
Source: https://github.com/DogStraight/trans-paradigm-compiler
License: MIT
```

署名单一来源：`packaging/attribution.py`（改作者/邮箱/仓库只改这里，重新打包）。
AI 协作者（deepseek-v4-flash，0.1.0 起署名）：项目语法包/引擎/验证由模型
辅助开发，作为协作者正式列入署名（pyproject.toml authors 同步）。

## 产物验证（2026-08-22 实测）

| 用例 | tpc-fmt | tpc-lint |
|---|---|---|
| `--version` / `--credits` | 正常（exit 0） | 正常 |
| 输出与 `python main.py format/lint` 一致 | ✅ 逐字节 | ✅ |
| 自包含（从 `C:\` 绝对路径运行） | ✅ | ✅ |
| 切面裁剪（fmt 入口不接受 `lint`） | ✅ `{format}` 仅此 | ✅ `{lint}` 仅此 |
| 增强语法 / 坏输入门禁 | ✅ / lint 拦截 exit 1 | — |
| SHA256 | 写入 `dist/SHA256SUMS.txt` | 写入 |

## 构建要点（踩过的坑）

- `--include-data-dir` **必须绝对源路径**（Nuitka 按 spec 相对解析会找不到）；
  目标路径用 `/`。`grammar/verilog` 整树（含 `plugins/**/*.py`——插件 handler
  是运行时 importlib 动态加载的）必须捆绑。
- 引擎路径解析（`core/define.py` root 定位）在 Nuitka 下与 dev/wheel 一致。
- 生成入口在 `packaging/entries/`（gitignored，不入库）；入口文件名下划线，
  exe 名保留连字符（`tpc-fmt.exe`）。
- **Nuitka 模块缓存会串旧入口内容**（实测：换入口后不清理缓存，exe 载荷仍是
  旧入口编译产物——`--credits` 打出旧文本）。管线已强制 `--clean-cache=all`
  （打包低频，每次全量重编译，正确性优先）。

## 限制

- **Windows 单平台**：本机构建产物仅 Windows；其他平台需在该平台重新构建。
- **未签名**：SmartScreen 警告无法避免，代码签名是发布时的事。
- **首次运行解压**：onefile 模式每次运行解压到临时目录（~1-2 秒）。
- **语法配置内嵌**：修改 grammar/ 后需重新打包。
- **版本内嵌**：`--version`/PE 版本来自 `core/__init__.py.__version__`，与引擎
  同源（打包管线构建时读取，单一来源）。

## 与发布的关系

切面 exe 是"薄片交付"形态——不替代 PyPI 包（`pip install trans-paradigm-compiler`
提供完整 `tpc` CLI），是给不想装 Python 的用户的独立分发通道。
