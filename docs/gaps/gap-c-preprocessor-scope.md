# Gap — C 预处理器范围基线（宏与预处理指令集；`ROADMAP.md` 阶段 4）

- 状态：未立项（**范围基线已定**：作者 2026-10-17 裁定"**只考虑 C 标准中的宏**"——特定编译器才需求实现的宏不考虑；文本级宏处理，卫生宏=语法结构、过程宏=能力位，均不在此范围；未开工）
- 关联：`ROADMAP.md`「C 语言包」阶段 4；`preprocessor/README.md`（跨语言文本能力原型）
- 接受面证据：`tools/c_acceptance.py`（当前 **接受 40 / 空洞 2**，空洞 = `#include` / `#define`）

## 方法（可复跑：机械区分"标准项 vs 编译器扩展"）

**手段**：用 GCC 逐档 `-std=<c99|c11|c17|c23> -pedantic-errors` 编译同一用例——GCC 的 pedantic 诊断会**点名标准版本**（如 `'__VA_OPT__' is not available until C23`、`'#warning' before C23 is a GCC extension`），于是"该特性属哪个标准档"变成可观测事实，不必依赖记忆的条款号。**被测编译器**：本机 `gcc (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r4) 16.1.0`。

复跑（单行，改 `SRC` 与 `--std` 即可；WSL/Linux 同形）：

```powershell
python -c "import subprocess,tempfile,pathlib,sys; d=pathlib.Path(tempfile.mkdtemp()); p=d/'t.c'; p.write_text('#warning w\n'); r=subprocess.run(['gcc','--std=c17','-pedantic-errors','-E',str(p)],capture_output=True,text=True); sys.stdout.write(r.stderr or 'OK')"
```

**局限（本档标"待抽检"的直接原因）**：编译器**不表态**的特性该方法**判不了**——`__has_include` / `#elifdef` / `#elifndef` / `__has_c_attribute` / `__COUNTER__` / `#pragma once` 在四档 pedantic 下**都不报错**（C23 标准项与静默接受的扩展无法区分）⇒ 这些项的归位只能靠**标准正文**，属**引用级**。

## 范围 = C 标准宏集

档位口径（本档自定，供排期；非标准术语）：**A** = 不实现就过不了真实 C 源；**B** = 标准要求且真实源常见；**C** = 标准要求但少见/新（C23 面）。

### 指令

| 指令 | 标准档 | 档位 | 判据（一句话） |
|---|---|---|---|
| `#include` | C99 原有 | A | `""` 先本文件目录、`<>` 只走 `-I`；缺文件必须报错（POSIX `c99` 已规范搜索序与 `-I` 容量下限） |
| `#define`（对象宏 / 函数宏） | C99 原有 | A | 宏体替换 + 实参替换；函数宏形参表可空 |
| `#undef` | C99 原有 | A | 取消定义；未定义者 `#undef` 合法 |
| `#if` / `#ifdef` / `#ifndef` / `#elif` / `#else` / `#endif` | C99 原有 | A | 条件表达式按整型常量表达式求值（`defined` 两种写法）；未闭合 `#if` 与多余 `#endif` 必须报错 |
| `#line` | C99 原有 | B | 改变后续 `__LINE__`/`__FILE__` 与诊断位置 |
| `#error` | C99 原有 | B | 立即报错（负样本用） |
| `#pragma` | C99 原有（**语义实现定义**） | B | 引擎不解释：**保真穿透**（`-E` 下允许复制到输出） |
| `#`（空指令） | C99 原有 | B | 一行只有 `#` ⇒ 无效果 |
| `_Pragma`（算子） | **C99 新增** | B | 等价 `#pragma` 的表达式形态 |
| `#elifdef` / `#elifndef` | **C23 新增（待抽检）** | C | `#ifdef`/`#ifndef` 的续接形态；⚠ 属**标准项**，不得当扩展排除 |
| `#warning` | **C23 新增** | C | 诊断但不中断（实测：c17 报 "before C23 is a GCC extension"，c23 通过） |
| `#embed` | **C23 新增** | C | 二进制资源嵌入；配套 `__STDC_EMBED_{FOUND,NOT_FOUND,EMPTY}__`（待抽检） |

### 宏算子与语义

| 项 | 标准档 | 档位 | 判据 |
|---|---|---|---|
| `#`（字符串化） | C99 原有 | A | 实参**先不展开**再字符串化 |
| `##`（粘贴） | C99 原有 | A | 用**未展开拼写**粘贴（`CAT(EMPTY,x)`→`EMPTYx`，与 GCC 实测一致） |
| **重扫描 / 自引用抑制** | C99 原有 | A | `#define x x` 保持 `x`；互递归 `y→z→y` 停在 `z`（不得无限展开） |
| 实参替换（含空实参） | C99 原有 | A | 空实参保留逗号：`F(1)`（`f(a,__VA_ARGS__)`）→ `f(1, )`（标准行为） |
| `__VA_ARGS__` | **C99 新增** | A | 变参宏的占位标识符 |
| `__VA_OPT__` | **C23 新增** | C | 标准化的"条件内容"；**与 GNU `, ## __VA_ARGS__` 是两件事**（见下表） |
| GNU `, ## __VA_ARGS__` | **扩展（排除）** | — | 语法糖式"删逗号"；C23 的对应标准写法是 `__VA_OPT__(,)`。**排除但登记触发条件**（裁定 4） |
| GNU 命名变参 `#define F(args...)` | **扩展（排除）** | — | 标准无命名变参 |

### 预定义宏

| 宏 | 标准档 | 档位 | 判据 |
|---|---|---|---|
| `__FILE__` `__LINE__` `__DATE__` `__TIME__` | C99 原有 | A | 展开期取当前文件/行/编译时间 |
| `__STDC__` `__STDC_HOSTED__` | C99 原有 | A | 分别为 `1` / 宿主实现标志 |
| `__STDC_VERSION__` | C99 原有 | A | **实测四档值**：`c99=199901L`、`c11=201112L`、`c17=201710L`、`c23=202311L`（须随档位变化） |
| `__STDC_ISO_10646__` / `__STDC_MB_MIGHT_NEQ_WC__` / `__STDC_UTF_16__`·`__STDC_UTF_32__`(C11) / `__STDC_LIB_EXT1__` / `__STDC_NO_*__`(C11) | C99/C11（**条件定义**） | C | 可以不定义；不得无条件定义（条款号待抽检） |
| `__has_include` / `__has_c_attribute` / `__has_embed`（C23） | **C23 新增（待抽检）** | C | ⚠ 早期为 GCC/Clang 扩展，**C23 已标准化** ⇒ 按标准项收录，不得当扩展排除 |
| `__func__` | C99 原有 | 不适用 | **预定义标识符，不是宏** ⇒ 不属本档（除非 tpc 主动扩展） |

## 扩展排除表（逐条依据 = 哪档 GCC 报什么 / 为何仍属扩展）

| 扩展 | 依据 |
|---|---|
| `, ## __VA_ARGS__` | c17 pedantic：`ISO C99 requires at least one argument for the "..." in a variadic macro`；标准对应物为 `__VA_OPT__(,)`（⚠ c23 档 GCC 不再报错，但**仍是 GNU 扩展**） |
| GNU 命名变参 `args...` | c23 pedantic 仍报 ISO C 不符 |
| `#include_next` | 各档 pedantic：`'#include_next' is a GCC extension` |
| `#pragma once` | 各档**不报错**（静默接受）⇒ **引用级**（标准 §6.10.6 语义实现定义） |
| `__COUNTER__` | 各档不报错 ⇒ **引用级**（标准预定义宏清单无它） |
| `__has_builtin` / `__has_feature` / `__has_attribute` / `__has_extension` | Clang/GCC 扩展（标准只有 `__has_include`/`__has_c_attribute`/`__has_embed`） |
| `__TIMESTAMP__` / `__BASE_FILE__` / `__FILE_NAME__` / `__INCLUDE_LEVEL__` | 编译器扩展 ⇒ 引用级 |
| `#ident` / `#sccs` / `#import` | 历史/厂商扩展 ⇒ 引用级 |
| 具名 `#pragma`（`GCC …`/`pack`/`message`） | 语义实现定义 ⇒ tpc 策略 = **保真穿透**，不逐条实现 |

## tpc 承载面与缺口

**现役承载面（实测）**：指令原语注册表 `preprocessor/primitives/registry.py` 已注册 **8 个**——`define`（对象宏 + 函数宏形参表）/ `undef` / `include`（`path_forms`=开闭定界符+`relative_first`、`search_dirs`、`silent`）/ `ifdef` / `ifndef` / `else` / `elsif` / `endif`；声明面 `[macro_recognition]`（`shape`/`directive`/`call`/`call_args`/`arg_separator`）与 `[directive_handlers]`（关键字→`op` + 每指令配置）；三机制 `splice`/`line`/`inline` + 位置桥（锚 + `source_text` 回插）。
**关键现状**：`grammar/c/` **完全没有** `[macro_recognition]` / `[directive_handlers]`（全仓仅 `grammar/verilog/` 声明）。

| 缺口 | 形态 | 现有能力能否承载 |
|---|---|---|
| ① **C 裸标识符宏调用**（`NAME` / `NAME(args)`） | 机制级 | **不能**：`shape` 实测要求"前缀 token 名 + 名字位"**两位、前缀位不能空**（`preprocessor/macro_shape.py` 的 shape 解析 fail-fast）；且宏调用与普通标识符同形，需按宏表判定 |
| ② `#` / `##` + **重扫描/自引用抑制** | 机制级 | **不能**：现为文本替换 + `[expand] max_iterations` 封顶，无消解语义 |
| ③ `#if` / `#elif` 的**整型常量表达式求值** | 机制级 | **不能**：现有 `elsif` 是"宏名"语义，非表达式求值 |
| ④ **预定义宏注入**（`__FILE__`…/`__STDC_VERSION__`） | 机制级 | **不能**：无预定义宏面 |
| ⑤ 指令前缀与行首语义 | 声明面 | 部分：`#` 需作为符号 token 声明；`#` 与关键字间空白、行首（前导空白）容差待验证 |
| ⑥ `#line` / `#error` / `#pragma` / `_Pragma` | 原语 | 部分：`#pragma`/`_Pragma` 走"保真穿透 + marker"；`#line` 改变文件/行语义 ⇒ 与位置映射联动 |
| ⑦ 条件块内 / 跨文件（`#include`）位置映射 | 新面 | 部分：`preprocessor/_bridge.py` 逐宏调用可回插；条件块与跨文件映射需新账本 |

**根因一条（实测）**：`grammar/c/base/_token.toml` 的 `[symbol.base]`（16 项单字符符号）里**没有 `#`**（`##` 亦无）⇒ 这就是 `tools/c_acceptance.py` 报 `Unexpected token: #` 的原因，也是缺口 ①②③④ 之外最前置的一条。

## 可实现性：首片 A / B（可独立验证）

- **首片 A（闭合两个空洞）**：`#define`（对象 + 函数宏 + `#` + `##` + `__VA_ARGS__` + 重扫描消解）、`#include`（`""`/`<>` + `-I` + 缺文件报错）、`#undef`、**裸标识符调用识别**。
  **验收面（现成）**：`python tools/c_acceptance.py --only-gaps` 的两条空洞（`#include` / `#define`）**归零**。
- **首片 B**：`#if` 家族（`defined` 两写法 + 整型常量表达式）+ `#line` + `#error`。
- **不做**：C23 档 C 项（`#warning`/`#elifdef`/`#elifndef`/`#embed`/`__VA_OPT__`/`__has_*`）不进首片（保留在清单）；全部 GNU 扩展（见排除表）。
- **正/负样本（与 GCC 对拍）**：正 = `#define x x`→`x`、`CAT(EMPTY,x)`→`EMPTYx`、`F(1)`→`f(1, )`；负 = 未闭合 `#if`、多余 `#endif`、`#include` 缺文件、`#define` 形参表未闭合（须报错）。
- **保真/幂等**：展开产物经位置桥回插后逐字节还原原文；复跑稳定（复用管线既有幂等检查口径）。

## 裁定（已定 / 待决）

**已定方向**：① C23 档 C 项**不进首片**（保留在清单）；② GNU `, ## __VA_ARGS__` **排除**（不实现其语义），**登记触发条件**：若真实 C 语料大量出现 ⇒ 复议；③ `preprocessor/primitives/define.py` 的"**形参表未闭合 ⇒ 容错退化为对象宏**"改为 **fail-fast**（依"配置加载 fail-fast / 不静默降级"纪律；实现时附影响面实测）。
**待作者确认**：④ `__STDC_VERSION__` 值的**声明位置**（引擎 vs 语言包声明键）与 `#if` **整型求值语义档**属**同一待决点**——涉新增声明键，**不自行定**。

## 诚实边界（统一"待抽检"，不得当实测结论用）

- ISO C 条款号（§6.10.x）为**记忆级**；**C23 子条编号未核实**（本机无标准正文；`cppreference`、`gcc.gnu.org` 均 403）。
- 编译器**静默接受**的项（`#pragma once` / `__COUNTER__` / `__has_include` / `#elifdef` / `__has_c_attribute`）属**引用级** ⇒ 归位待抽检（方法局限见上文）。
- 本档"实测"仅指：本机 GCC 16.1.0 的逐档 pedantic 行为、`__STDC_VERSION__` 四档值、`tools/c_acceptance.py` 现状、仓库代码定位。

## 关联条目

- 路线：`ROADMAP.md`「C 语言包」阶段 4（预处理器，接受面仅剩空洞）
- 机制：`preprocessor/README.md`（宏形态声明 / 三机制 / 位置桥）、`grammar/verilog/base/_macro.toml`（声明面先例）
- 接受面：`tools/c_acceptance.py`（2 条预处理空洞）
- 门禁：`tests/engine/preprocessor/`（预处理器面）、`tests/languages/c/`（C 包）
- 相邻档：`docs/gaps/gap-c-semantic-base.md`（C 语义基座）、`docs/gaps/gap-language-pack-scope.md`（C 包接受域/档位）
