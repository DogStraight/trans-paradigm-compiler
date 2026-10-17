# Gap — C 预处理器范围基线（宏与预处理指令集；`ROADMAP.md` 阶段 4）

- 状态：**首片 A1 已交付**（2026-10-17，循环 #15：宏核心见 ⑯）；**A2 未开工**。范围基线已定（作者
  2026-10-17 裁定"**只考虑 C 标准中的宏**"——特定编译器才需求实现的宏不考虑；文本级宏处理，
  卫生宏=语法结构、过程宏=能力位，均不在此范围）
- 关联：`ROADMAP.md`「C 语言包」阶段 4；`preprocessor/README.md`（跨语言文本能力原型）
- 接受面证据：`tools/c_acceptance.py`（当前 **42 条 / 接受 42 / 空洞 0**）——**口径注**：两条预处理
  用例按"**被消费且无异常**"接受（指令行被替换为整行 marker 注释），**不代表 `#include` / `#define`
  已真实实现**；拆步信号以本节 ⑭ 为准

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
  **验收面（口径已修正，见 ⑭）**：`python tools/c_acceptance.py --only-gaps` 的计数**不再是拆步信号**
（放宽后已被"被消费 ⇒ 空 TU ⇒ 接受"掩盖）——**A1 信号 = 引擎核判据**（与 GCC 对拍的正样本 +
预处理器缺陷态变红）；**A2 信号 = `#include` 被真实处理**（`path_forms` 解析生效 + 缺文件**报诊断** +
内容确实被消费进流），**不是"空洞归零"**。
- **首片 B**：`#if` 家族（`defined` 两写法 + 整型常量表达式）+ `#line` + `#error`。
- **不做**：C23 档 C 项（`#warning`/`#elifdef`/`#elifndef`/`#embed`/`__VA_OPT__`/`__has_*`）不进首片（保留在清单）；全部 GNU 扩展（见排除表）。
- **正/负样本（与 GCC 对拍）**：正 = `#define x x`→`x`、`CAT(EMPTY,x)`→`EMPTYx`、`F(1)`→`f(1, )`；负 = 未闭合 `#if`、多余 `#endif`、`#include` 缺文件、`#define` 形参表未闭合（须报错）。
- **保真/幂等**：展开产物经位置桥回插后逐字节还原原文；复跑稳定（复用管线既有幂等检查口径）。

## 裁定（已定 / 待决）

**已定方向**：① C23 档 C 项**不进首片**（保留在清单）；② GNU `, ## __VA_ARGS__` **排除**（不实现其语义），**登记触发条件**：若真实 C 语料大量出现 ⇒ 复议；③ `preprocessor/primitives/define.py` 的"**形参表未闭合 ⇒ 容错退化为对象宏**"改为 **fail-fast**（依"配置加载 fail-fast / 不静默降级"纪律；实现时附影响面实测）；
⑤ **C 裸标识符宏调用的前缀 = 语言包显式声明"无前缀"**（Lead 2026-10-17 裁定；**不是**引擎默认允许空前缀——否则 verilog 侧"任何标识符都成宏调用候选"会引入**全域误匹配面**）；守"**不留双路径**"：有无前缀走**同一套**匹配路径；
⑥ **`__STDC_VERSION__` 值与 `#if` 整型求值语义都放语言包声明面**（Lead 同轮裁定：两者都是 C 特有语言知识，引擎不持有）；**具体声明键形态随首片 B 设计定**（`#if` 属首片 B）。

**待决**：无（原"④ `__STDC_VERSION__` 声明位置 / `#if` 求值语义档"已按 ⑥ 归位）。

**首片方案期追加裁定**（2026-10-17，承 task-48）：
⑦ **`call_shape = "name"`**（单元素生产式 = 显式"无前缀"；三态 `None`／`""`／非空；`shape` 仍两位 ⇒ **verilog 语义不变**）；
⑧ **`__DATE__`/`__TIME__` 永久排除**——**破坏幂等**（同输入两次运行展开不同），与 tpc 保真/复跑纪律冲突；
⑨ **`#include` 缺文件/循环由 `print` 改诊断**（不静默降级）但**放在 A2**，须附 **verilog 侧对拍 + 同步现役断言**；
⑩ **A1 完成按 `partial` 报**（拆步判据已由 ⑭ 修正为**引擎核判据**；`--only-gaps` 计数不作信号）。

**首片实施期裁定**（2026-10-17，承 task-49 中途汇报）：
⑪ **E.0 口径修正 = (a)+(c)**：`tools/c_acceptance.py::_try`（`:123-136`）**不走预处理**（直接 `parser.parse(lexer.tokenize(src))`）且要求 AST 非空 ⇒ 对预处理样本判定**失真**——`#define N 4` 的**正确**预处理结果本就是**空翻译单元** ⇒ 该样本**永远是"空 AST 空洞"**，原判据（"只剩 `#include`"）**不可达**。修正：**(a)** 改 `_try` 走"预处理→词法→解析"（与管线同路、开宏扫描）+ **对预处理样本接受条件放宽为"无异常"**（纯指令样本 AST 可空）；**非预处理样本仍须 AST 非空**（否则掩盖解析失败）；**(c)** 管线级测试补"指令被消费 + 无异常 + 输出保真"作双保险。**不采 (b)**（只改口径不修路径）。
⑫ **判据设计教训**：定"工具指标归零"类判据前**必须核实该工具的**真实执行路径**——本轮 Lead 未核实导致判据不可达（由实现方中途拦下）。
⑬ **已实测确认（真不一致、用户可见）**：`run_pipeline_on_source` 的 `expand_macros` **默认 False**（`pipeline/__init__.py:1161` + `config/tpc_config.json:12`）而 `tpc check` 默认 True（`analyzer/checker.py:57`、`main.py:132`）。实测（同输入 `#define N 4\nint x = N;`、同 API 只差该 flag）：**False ⇒ `error="parse truncated (unconsumed tokens)"`；True ⇒ `error=""`** ⇒ **verdict 差异**（非风格）。CLI 侧同文件对照：`tpc lint` rc=1 报 `phase-unrecognized`（line 0 col 8-9）｜`tpc check` rc=1 报 `parse_ok: false` 且 **`parse_error` 为空串** ⇒ 两条用户可见路径**彼此诊断形态也不同**。**归属 = 管线配置口径（非 C 专有，verilog 同样受"库默认 False"影响）**；**裁定 = 修（统一为"开"）**，归 **A2 步**（与"C 端到端可用"绑定），**必须附 verilog 对拍 + 行为变化清单**。
⑭ **拆步信号修正（因 ⑪ 放宽判据）**：`--only-gaps` 计数在放宽后**不可再用**作拆步信号——`#include <stdio.h>` 在 A1 阶段（`include` 未接线、只 `print` 警告）会因"被消费 ⇒ 空 TU ⇒ 接受"而**显示 0 空洞**，**掩盖"未实现"**。修正：**A1 信号 = 引擎核判据**（E.1 与 GCC 对拍的正样本 + E.4 的 5 条缺陷态变红）；**A2 信号 = `#include` 被真实处理**（`path_forms` 解析生效 + 缺文件**报诊断** + 内容确实被消费进流），**不是"空洞归零"**。
⑮ **文档漂移待 A1/A2 收口统一更新**（task-50 附带发现；**不现在改**，以免与在途结论打架）：A1 落地后以下**现状陈述已不成立**——① 本档状态行仍写"未开工"；② 本档缺口表 ①② 列"**不能**"（`call_shape` / hideset rescan 正在实现）；③ 本档"`[symbol.base]` **无 `#`** ⇒ acceptance 报 `Unexpected token: #` 的根因"（**根因已消除**：`#`/`##` 已声明；直连词法 `tokenize('#include <stdio.h>\n')` 已能切出 `macro.include` 且**不抛**）；④ 本档"首片 A（**闭合两个空洞**）"（按 ⑭ 不宜用计数表述）；⑤ `docs/gaps/gap-language-pack-scope.md` 已知偏差 #5 的复现命令与现象（"`#include` 在词法层直接 ValueError"）**已随 A1 失效**。⇒ **A2 收口时逐条复核并更新**。

⑯ **A1 交付实录（2026-10-17，循环 #15）**：已完成面 = `#define`（对象/函数/变参）+ `#undef` + **C 裸标识符调用**（`call_shape="name"` 显式无前缀，三态，verilog 语义不变）+ `#` 字符串化（token 间空白折叠，字面量内部不动）+ `##` 粘贴（**未展开拼写**）+ `__VA_ARGS__`（空时保留宏体逗号）+ **hideset 重扫描**（替换不动点文本替换）+ **掩码**（含替换进流的宏体）+ 形参表未闭合 **fail-fast**。验证 = GCC 16.1.0 对拍（Lead 独立探针）+ 六套回归 2257 + A/B 0/144 + 门禁变异 57→65（A1 8 条全红）。**审计发现**：① 宏体字面量未掩码的真 bug（`#define B "A"` 误展开，已修）；② 两条测试空档（hideset 断言太弱、宏体掩码路径）已补判别式用例；③ 一条等价变异不可检出，已删。**未做（A2）**：`#include` 真实实现、管线段与 lint 两路径统一、`expand_macros` 默认口径；`#if` 家族与 C23 项归首片 B/后续。

## 诚实边界（统一"待抽检"，不得当实测结论用）

- ISO C 条款号（§6.10.x）为**记忆级**；**C23 子条编号未核实**（本机无标准正文；`cppreference`、`gcc.gnu.org` 均 403）。
- 编译器**静默接受**的项（`#pragma once` / `__COUNTER__` / `__has_include` / `#elifdef` / `__has_c_attribute`）属**引用级** ⇒ 归位待抽检（方法局限见上文）。
- 本档"实测"仅指：本机 GCC 16.1.0 的逐档 pedantic 行为、`__STDC_VERSION__` 四档值、`tools/c_acceptance.py` 现状、仓库代码定位。

## 关联条目

- 路线：`ROADMAP.md`「C 语言包」阶段 4（预处理器；能力面缺口仍在，工具计数口径见 ⑭）
- 机制：`preprocessor/README.md`（宏形态声明 / 三机制 / 位置桥）、`grammar/verilog/base/_macro.toml`（声明面先例）
- 接受面：`tools/c_acceptance.py`（**42 条 / 接受 42 / 空洞 0**；两条预处理用例按"被消费且无异常"接受，**不代表已真实实现**——口径见 ⑭）
- 门禁：`tests/engine/preprocessor/`（预处理器面）、`tests/languages/c/`（C 包）
- 相邻档：`docs/gaps/gap-c-semantic-base.md`（C 语义基座）、`docs/gaps/gap-language-pack-scope.md`（C 包接受域/档位）
