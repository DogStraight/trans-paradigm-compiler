"""tools/check_gate_efficacy.py — 门禁有效性抽查（变异测试的清单化版本）。

Doc: AGENTS.md（运行节：测试门禁）

动机：门禁的全部价值在于它会红——但这个性质是门禁自身的属性，**没有任何
测试在测它**。历史上这里做过几次回退验证（把修复改回去、确认测试变红），
那些动作都是一次性的：门禁哪天失效没人知道，而"绿"看起来完全一样。

做法：清单里每条变异都**来自真实发生过的事故**（不是想象的），逐条执行
    备份 → 应用文本变异 → 跑指定测试 → **期望失败** → 还原
若在某条变异下测试仍然通过，说明该门禁已失效（或测试被削弱）→ 报错。

设计取舍：
- **变异点只从真实事故取**：想象的变异无法证明门禁挡住了它该挡的东西；
  每条都带 `why`（当年怎么发现的），让清单本身可审查。
- **测试用文件级而非用例级**：源码重构会改名用例，文件级更稳（本清单要活
  很久，锚点漂移的代价高于精确度收益）；文件里任一用例变红即算通过。
- **锚点找不到就报错**：源码变了导致变异无法施加时，报清单过时而非静默
  跳过——静默跳过会让抽查慢慢变成空转（和门禁假绿同一个病）。
- **不进日常门禁**：每条要跑一次相关测试，全清约一分钟；定位同
  `eval_benchmark.py`（人工/定期跑）。
- **要求工作区干净**：变异会临时改写源码，脏工作区下还原会掩盖未提交改动。

用法：
    python tools/check_gate_efficacy.py            # 跑全部变异
    python tools/check_gate_efficacy.py --list     # 只列清单
    python tools/check_gate_efficacy.py --only 3   # 只跑第 3 条（从 1 起）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 每条变异 = 一个真实事故 + 它应该触发的那道门。
_MUTATIONS: list[dict[str, str]] = [
    {
        "why": "NC008 曾长期是死规则：GenvarDecl 的 name_attr 取不到名字 → 符号"
               "从未注册 → 判定永不触发（0.1.2 收尾轮评测扩面时发现）",
        "file": "grammar/verilog/02_declarations/40_params.toml",
        "old": 'name_attr = "genvar_names.content"',
        "new": 'name_attr = "genvar_names.name"',
        "test": "tests/languages/verilog/test_name_convention.py",
    },
    {
        "why": "slot_runner 的 result=extra 曾误把 handler 返回值接回 AST → typed_ports"
               " wrapper 被内联进主输出（保真度 1.0→0.43），由真实语料 e2e 抓到",
        "file": "transform/slot_runner.py",
        # ⚠ 载荷随目标代码重排同步更新过（2026-09-25）：旧片段是 16 空格缩进 + 行内
        # 注释的写法，注释迁进 docstring 后失配——**变异失效本身就是门禁失效**，
        # 由 tests/policy/test_gate_efficacy_mutations.py 静态守住。
        "old": "        if result == \"extra\":\n"
               "            new.append(item)\n",
        "new": "        if result == \"extra\":\n"
               "            new.append(out if isinstance(out, Node) else item)\n",
        "test": "tests/engine/pipeline/test_unit_slot_schedule.py",
    },
    {
        "why": "MH002 的续行保守判定若被去掉，多行宏体会被误判为值不同 → 误报"
               "（实现时即按宁可漏报定调，故该行为必须有测试锁住）",
        "file": "linter/checkers/macro_hygiene.py",
        "old": "        return name, None if (cont and body.endswith(cont)) else body",
        "new": "        return name, body",
        "test": "tests/engine/linter/test_linter_macro_hygiene.py",
    },
    {
        "why": "真实语料误报基线门禁（只许减不许增）：若基线被改小而门禁不报，"
               "整个误报面不无声增长的保障就是空的",
        "file": "tests/e2e/samples/real/diag_baseline.json",
        "old": '    "W105": 2,',
        "new": '    "W105": 0,',
        "test": "tests/policy/test_diag_baseline.py",
    },
    {
        "why": "语言作用域重置（2026-09-14 实测事故：同进程先跑 c4 再跑 verilog，"
               "规则表跨语言累积 → 根规则被 c4 的 Program 夺走 → 输出为空；"
               "该现象曾被当作'幽灵 flake'）",
        "file": "parser/__init__.py",
        "old": "    register.begin_language(rules_dir)\n",
        "new": "    pass  # 变异：关掉语言作用域重置\n",
        "test": "tests/engine/core/test_language_switch.py",
    },
    {
        "why": "匹配器把「必选 call 零进展」当空匹配成功（旧判据 `len(sub_errs) == before`）"
               "→ 失败的规则被静默跳过、后续元素在错位上继续匹配：C 包合法头文件上"
               "14 条结构误报，合法代码 linter 全报（2026-09-26 定位并修复）",
        "file": "linter/checkers/matcher.py",
        "old": """        typ = feat.get("type")
        if typ in ("optional", "repeat"):
            return True
        if typ == "call":
            name = feat.get("name", "")
            cached = self._nullable_cache.get(name)
            if cached is None:
                cached = _rule_nullable(name, self._tree, set())
                self._nullable_cache[name] = cached
            return cached
        return False""",
        "new": """        typ = feat.get("type")
        if typ == "optional":
            return True
        return typ in ("call", "repeat") and len(sub_errs) == before""",
        "test": "tests/languages/c/test_c_corpus.py",
    },
    {
        "why": "seq 内「可空元素零进展」被当整体失败 → 单元素初始化列表等形态解不出："
               "C 包 `{.k = 0}` / `int a[4] = {1};` / `{ {1} }` 报 expected ';' got '{'"
               "（同轮定位，`_match_seq` 的零进展判据）",
        "file": "linter/checkers/matcher.py",
        "old": """            if j <= i:
                # 零进展：optional 不存在 / repeat 匹配 0 次（如
                # `(@InitElement,(comma,@InitElement)*)?` 的单元素形态）/
                # 可空 call —— 这些都合法，跳过继续；其余（token 失败、
                # seq 内必选 call 失败）才整体回滚，防止后续元素在未推进
                # 位置假匹配（如 Range 的 l_square 失败后 @Expression 误吞
                # `=` 导致 repeat 无限推进）。
                if not self._no_progress_ok(item, errors, before):
                    return start
                continue""",
        "new": """            if j <= i:
                return start""",
        "test": "tests/languages/c/test_c_corpus_impl.py",
    },
    {
        "why": "discovery 的 `_advance_match` 对零进展元素做 `j + 1` 兜底 → 紧随其后的"
               "元素从错位 token 起匹配：C 包函数定义的 body 起点被算到参数位，"
               "多注册一个假子节点并误报（同轮定位）",
        "file": "linter/discovery.py",
        "old": "            return matcher.match(tokens, j, feat, trial, end, strict=True)\n",
        "new": """            k = matcher.match(tokens, j, feat, trial, end, strict=True)
            return k if k > j else j + 1
""",
        "test": "tests/languages/c/test_c_corpus_impl.py",
    },
    {
        "why": "discovery 的括号分支不把「块规则」转块分支 → 块内语句既不解析也不诊断"
               "（静默漏检，c4 的缺分号一度靠 `j + 1` 巧合发现才没暴露；同轮定位）",
        "file": "linter/discovery.py",
        "old": """        if candidates and isinstance(candidates[0], str):
            info = self._tree.get(candidates[0], {}) or {}
            if info.get("block_end"):
                return self._discover_block(
                    tokens, i, end, context, depth, nodes, record=record
                )
""",
        "new": "",
        "test": "tests/languages/c4/test_c4_linter.py",
    },
    {
        "why": "括号定界容器体的位点发现被摘掉（P3c 前置切片）→ production 层语句位"
               "（C 函数体 / 块内语句位）不再产生未收敛位点 ⇒ raw 承载将无位点可消费",
        "file": "linter/discovery.py",
        "old": "                self._scan_container_sites(tokens, i, e, candidates[0], context, depth)\n",
        "new": "",
        "test": "tests/engine/linter/test_linter_raw_eligibility.py",
    },
    {
        "why": "lexer 最长匹配要求「每层中间前缀自身也声明过」→ 中间形态未声明的符号永远"
               "匹配不到：C 的 `...` 被降级成三个 `.`，变参原型整条解析失败 + linter 误报"
               "（yaml/verilog 曾各塞一个『仅为 probe 链』的 `..` 占位声明绕开它）",
        "file": "lexer/main_lexer.py",
        "old": """        start = st.idx
        best = st.text[start]
        best_len = 1
        j = start + 1
        while j < st.text_len:
            probe = st.text[start : j + 1]
            if probe in self._extend_set:
                best, best_len = probe, j + 1 - start
            elif probe not in self._extend_prefixes:
                break
            j += 1
        tok.set_content(best)
        tok.set_type("symbol.extend" if best_len > 1 else "symbol.base")
        st.idx = start + best_len
        st.offset = best_len
""",
        "new": """        tok.set_content(st.text[st.idx])
        tok.set_type("symbol.base")
        st.idx += 1
        st.offset += 1
        candidate = tok.content
        while st.idx < st.text_len:
            probe = candidate + st.text[st.idx]
            if probe in self._extend_set:
                candidate = probe
                st.idx += 1
                st.offset += 1
            else:
                break
        if len(candidate) > 1:
            tok.set_content(candidate)
            tok.set_type("symbol.extend")
""",
        "test": "tests/engine/lexer/test_lexer.py",
    },
    {
        "why": "C 的变参尾段 `...` 曾被记为「需引擎侧形态」的缺口（三种配置写法全部证伪）"
               "——真根因是 lexer 最长匹配缺陷 + token 类型写成 symbol.base.ellipsis；"
               "去掉配置里的尾段交替后变参原型不再进 AST（且 linter 会误报合法代码）",
        "file": "grammar/c/01_declarations.toml",
        "old": """    "@ParamDecl",
    "(symbol.base.comma,(@ParamDecl|symbol.extend.ellipsis))*",
""",
        "new": """    "@ParamDecl",
    "(symbol.base.comma,@ParamDecl)*",
""",
        "test": "tests/languages/c/test_c_declarations.py",
    },
    {
        "why": "沉淀语料的抬头判定与所在目录不一致（把 reject 写成 clean）→ 门禁会在"
               "错误方向锁行为：抬头是给人看的，也是 run_edge 复检不变量的登记项",
        "file": "tests/edge/edge_corpus/reject/truncated_garbage.v",
        "old": "// edge reject（fuzz 回归 2026-08-22）",
        "new": "// edge clean（fuzz 回归 2026-08-22）",
        "test": "tests/policy/test_edge_corpus_provenance.py",
    },
    {
        "why": "收缩/沉淀链路的「未修不沉淀」闸被拆 → 未修缺陷会被固化成期望行为"
               "（实测踩过：非幂等样本 success=True，只按 clean/reject 判会写进 clean/）",
        "file": "tests/fuzz/shrink.py",
        "old": "    if still_violates:\n",
        "new": "    if False:  # 变异：拆掉「未修不沉淀」闸\n",
        "test": "tests/policy/test_fuzz_shrink.py",
    },
    {
        "why": "edge 门禁不再复检沉淀语料抬头登记的不变量 → 只判 clean/reject 时"
               "「仍非幂等」这类活缺陷一路绿灯（实测踩过）",
        "file": "tests/edge/run_edge.py",
        "old": "    if kind in kinds:\n",
        "new": "    if False:  # 变异：不复检抬头登记的类别\n",
        "test": "tests/policy/test_fuzz_shrink.py",
    },
    {
        "why": "插件的注入声明被删（`_Alignof` 不再注进核心两处原子清单）→ 该增量静默失效"
               "（`_Alignof(int)` 解析不出 AlignofExpr）。注入是**声明面**：删掉声明后不该"
               "还有别的东西在背后兜着——本变异证明测试真的在守那行声明",
        "file": "grammar/c/plugins/c11/11_alignof.toml",
        "old": 'targets = ["@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"]\n',
        "new": "",
        "test": "tests/languages/c/test_c_increment_plugin.py",
    },
    {
        "why": "`_entries` 的来源判据只比目录、不比档位 → 同 pack 切档复用上一档声明"
               "（实测症状：`enabled=[]` 后仍解析出 StaticAssertDecl）。本变异证明"
               "三档矩阵真的在守那个二元判据",
        "file": "core/config_registry.py",
        "old": "        if cls._entries_source != candidate or cls._entries_enabled != tier:\n",
        "new": "        if cls._entries_source != candidate:\n",
        "test": "tests/languages/c/test_c_standard_tiers.py",
    },
    {
        "why": "`_resolve_cache` 的键不含档位 → 隐式消费方（Lexer 走 `resolve`）拿回上一档"
               "token（实测症状：切到基线档后 Lexer 仍带 `_Static_assert` 关键字）。"
               "本变异证明「Lexer 跟随档位」那条测试真的在守缓存键",
        "file": "core/config_registry.py",
        "old": """        cache_key = (
            candidate,
            tuple(ext_dirs) if ext_dirs else (),
            plugins_dir,
            frozenset(base_dirs.items()),
            tier,
        )
""",
        "new": """        cache_key = (
            candidate,
            tuple(ext_dirs) if ext_dirs else (),
            plugins_dir,
            frozenset(base_dirs.items()),
        )
""",
        "test": "tests/languages/c/test_c_standard_tiers.py",
    },
    {
        "why": "`_Atomic` 两形态**必须收在一条规则里**（可选组）。去掉那个 `?` ⇒"
               "限定符形态 `_Atomic int x;` 不再匹配（组变成必需）——本变异证明"
               "「两形态同环境并存」那条测试真的握着这个形态选择",
        "file": "grammar/c/plugins/c11/16_atomic.toml",
        "old": '    "(bracket.l_parentheses,@TypeName,bracket.r_parentheses)?",\n',
        "new": '    "(bracket.l_parentheses,@TypeName,bracket.r_parentheses)",\n',
        "test": "tests/languages/c/test_c_increment_plugin.py",
    },
    {
        "why": "`_Alignas` 的宿主必须是**被六处说明符位共同引用的 `TypeQualifier`**："
               "换成单点 `@Declaration.production[0]` ⇒ 结构成员/参数/类型名三处说明符位"
               "失效（A/B 实测的空 AST）。本变异证明那三条用例真的握着注入点选择",
        "file": "grammar/c/plugins/c11/15_alignas.toml",
        "old": '[AlignasConstSpec.inject]\ntargets = ["@TypeQualifier.production[0]"]\n',
        "new": (
            '[AlignasConstSpec.inject]\n'
            'targets = ["@Declaration.production[0]"]\n'
        ),
        "test": "tests/languages/c/test_c_increment_plugin.py",
    },
    {
        "why": "小写 `static_assert` 的**块作用域**靠 `targets = [\"@Stmt\"]` 这一行（旧注曾写"
               "『块作用域不可用，需改核心』）。删掉它 ⇒ 函数体内的 `static_assert(1,\"x\");`"
               "不再进 Stmt 交替——本变异证明那三条块作用域用例真的握着这行声明",
        "file": "grammar/c/plugins/c23/10_static_assert_alias.toml",
        "old": '[StaticAssertC23Decl.inject]\ntargets = ["@Stmt"]\n',
        "new": "",
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "`alignof` 是原子规则，必须注进**两处**原子清单（只注一处会得到「能当表达式、"
               "不能当后缀链头」的半通形态）。去掉 PostfixExpr 那处 ⇒ 「两处都在」的断言"
               "必须变红",
        "file": "grammar/c/plugins/c23/17_alignof_alias.toml",
        "old": 'targets = ["@PrimaryExpr.production[0]", "@PostfixExpr.production[0]"]\n',
        "new": 'targets = ["@PrimaryExpr.production[0]"]\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "`_BitInt(N)` 是类型词，必须挂**公共宿主 `SimpleType`**（一次注入多处生效）。"
               "换成单点 `@Declaration.production[0]` ⇒ 结构成员/参数/`sizeof` 三处失效"
               "——本变异证明那三条用例真的握着宿主选择（同 15_alignas 那条的教训）",
        "file": "grammar/c/plugins/c23/19_bitint.toml",
        "old": 'targets = ["@SimpleType.production[0]"]\n',
        "new": 'targets = ["@Declaration.production[0]"]\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "`[[属性]]` 挂 `TypeQualifier`（公共宿主）⇒ 说明符位 6 处 + \"属性声明\"一并生效。"
               "把宿主换成单点 `@Declaration.production[0]` ⇒ 结构成员/参数/`sizeof` 三处失效"
               "——本变异证明那三条属性用例真的握着宿主选择",
        "file": "grammar/c/plugins/c23/21_attributes.toml",
        "old": 'targets = ["@TypeQualifier.production[0]", "@AttributeSlot.production[0]"]\n',
        "new": 'targets = ["@Declaration.production[0]"]\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "声明符内 / 枚举项的属性位点靠**共用的空槽位** `@AttributeSlot`（一次注入两处生效，"
               "2026-09-28 起）——旧记载写「注入做不到这两个位点」。去掉这条 target ⇒ 槽位"
               "永远无形态 ⇒ 两个位点的属性整条声明解析不出来（空 AST）",
        "file": "grammar/c/plugins/c23/21_attributes.toml",
        "old": 'targets = ["@TypeQualifier.production[0]", "@AttributeSlot.production[0]"]\n',
        "new": 'targets = ["@TypeQualifier.production[0]"]\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "空槽位能被填充靠 `_inject_direct` 的**零长 append 分支**（旧实现 `if not prods:"
               " return` ⇒ 静默跳过）。把填充改回静默返回 ⇒ 空槽位永远无形态、属性两个"
               "位点解析不出来——本变异证明那条引擎分支不是装饰",
        "file": "parser/grammar_inject.py",
        "old": '        _write_prods(target_rule, [f"@{ext_rule_name}"])\n        return\n',
        "new": "        return\n",
        "test": "tests/engine/parser/test_grammar_inject.py",
    },
    {
        "why": "空槽位的 `$1` 绑定靠校验的 `empty_slot` 例外放行（上限按 1 算）。把上限改回"
               "`max_slot` ⇒ 加载 C 包时 `AttributeSlot` 的 `attrs = \"$1\"` 被判越界"
               "（配置 fail-fast 把空槽位当错）",
        "file": "core/define.py",
        "old": "        limit = 1 if empty_slot else max_slot\n",
        "new": "        limit = max_slot\n",
        "test": "tests/engine/core/test_rule_schema.py",
    },
    {
        "why": "`merge = \"by-name\"` 的核心是**同名条目深合并**（不是整体替换）——把"
               "`merge_by_name` 的同名分支改成直接替换 ⇒ C23 数字形态 `c_dec` 只剩插件那一小块"
               "（缺 size/base_prefix/value_digits）⇒ `1.5f`/`42u` 等核心后缀形态全崩。"
               "本变异证明引擎侧那条合并语义真的被握着",
        "file": "core/config_registry.py",
        "old": "            if key in index:\n                out[index[key]] = merge_by_name(out[index[key]], item)\n",
        "new": "            if key in index:\n                out[index[key]] = item\n",
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "插件声明**必须显式写** `merge = \"by-name\"` 才能与核心同名声明合并。去掉它 ⇒ "
               "该声明退回\"后者覆盖\"：核心 `[[number.based]]` 三条数字形态被整体顶掉"
               "（连 `1.5f` 都不再是数字 token）——本变异证明声明面的合并语义是必需的，"
               "不是装饰",
        "file": "grammar/c/plugins/c23/tpc.toml",
        "old": 'number = { file = "_number_c23.toml", section = "number", merge = "by-name" }\n',
        "new": 'number = { file = "_number_c23.toml", section = "number" }\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "跨语言配置串味的修点：`_push_loaded_config` 对「本包未声明的 key」必须**推回"
               "编译期默认**（旧实现什么都不推 ⇒ 留着上一个语言的值 ⇒ C 源上跑 verilog 的"
               "排版检查、长行报 ST003）。把默认推送去掉 ⇒ 两条新判据必红",
        "file": "core/config_registry.py",
        "old": "                if key in _CONFIG_DEFAULTS:\n                    setattr(mod, var_name, copy.deepcopy(_CONFIG_DEFAULTS[key]))\n                continue\n",
        "new": "                continue\n",
        "test": "tests/engine/core/test_config_loading.py",
    },
    {
        "why": "属性表尾逗号（C23 `attribute-list: attribute-list , attribute(opt)`）必须**独立"
               "绑定**：production 里加了 `(comma)?` 却不绑定 ⇒ 渲染器静默丢一个显著 token"
               "（`[[nodiscard,]]` 渲成 `[[nodiscard]]`）。本变异证明那条绑定判据真的握着它",
        "file": "grammar/c/plugins/c23/21_attributes.toml",
        "old": 'trailing_comma = "$3"\n',
        "new": "",
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "多实参属性（`[[gnu::nonnull(1, 2)]]`，glibc/clang 头文件常见）靠实参收 "
               "`@ArgumentList`：退回 assignment 层级的 `@Expression`（不含逗号）⇒ 多实参整条"
               "失配。本变异证明 `@ArgumentList` 这个宿主选择不是随手写的",
        "file": "grammar/c/plugins/c23/21_attributes.toml",
        "old": '    "(bracket.l_parentheses,@ArgumentList,bracket.r_parentheses)?",\n',
        "new": '    "(bracket.l_parentheses,@Expression,bracket.r_parentheses)?",\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "FOLLOW 传播必须递归进元素内部（备选支/分组/后缀组）：去掉 `_propagate_seq` 里"
               "那次结构级调用 ⇒ 备选支内序列尾部 call 拿不到后继（c4 `IndexExpr` 的 `]` 缺项，"
               "9 个下标形态匹配期被拒）。本变异证明那条递归不是冗余",
        "file": "parser/follow.py",
        "old": "        if _propagate_intra(\n            follows, elem, owner, beta_first, beta_nullable, first_map, nullable_map\n        ):\n            changed = True\n",
        "new": "",
        "test": "tests/engine/parser/test_follow.py",
    },
    {
        "why": "同上，但收窄到 `_propagate_intra` 的 **choice 分支**：不递归进备选内部 ⇒ "
               "备选支尾部失传（c4 下标 + `[[deprecated(\"a\" \"b\")]]` 那类写法）。"
               "本变异证明 choice 分支单独被握着",
        "file": "parser/follow.py",
        "old": '    if typ == "choice":\n        changed = False\n        for alt in elem.get("alternatives", []):\n            changed |= _propagate_intra(\n                follows, alt, owner, beta_first, beta_nullable, first_map, nullable_map\n            )\n        return changed\n',
        "new": '    if typ == "choice":\n        return False\n',
        "test": "tests/engine/parser/test_follow.py",
    },
    {
        "why": "`token_in_follow` 是 FOLLOW 的**唯一消费口**（返 True 恒通过）：把它短路 ⇒ "
               "后继检查整体失效。本变异守的是「检查本身还在执行」",
        "file": "parser/follow.py",
        "old": "    for member in follow:\n",
        "new": "    return True  # 变异：FOLLOW 检查失效\n    for member in follow:\n",
        "test": "tests/engine/parser/test_follow.py",
    },
    {
        "why": "负向守卫：choice 各支**不得**互当前继（把各支 FIRST 并进 beta 的过度包含写法）"
               "⇒ `(@X|kw.y)` 负向用例必红。本变异证明「别过度近似」这条判据有效",
        "file": "parser/follow.py",
        "old": '    if typ == "choice":\n        changed = False\n        for alt in elem.get("alternatives", []):\n            changed |= _propagate_intra(\n                follows, alt, owner, beta_first, beta_nullable, first_map, nullable_map\n            )\n        return changed\n',
        "new": '    if typ == "choice":\n        shared = set(beta_first)\n        for alt in elem.get("alternatives", []):\n            shared |= _elem_first(alt, first_map, nullable_map)\n        changed = False\n        for alt in elem.get("alternatives", []):\n            changed |= _propagate_intra(\n                follows, alt, owner, shared, beta_nullable, first_map, nullable_map\n            )\n        return changed\n',
        "test": "tests/engine/parser/test_follow.py",
    },
    {
        "why": "repeat/plus 的**循环后继**（下一次迭代 FIRST）是 c4 下标链（`a[0][f(1)]`）能解析的"
               "关键：去掉该分支 ⇒ c4 下标用例大面积红。本变异证明循环后继分支被握着",
        "file": "parser/follow.py",
        "old": '    if typ in ("repeat", "plus"):\n        return _propagate_intra(\n            follows,\n            elem.get("elem", {}),\n            owner,\n            beta_first | _elem_first(elem, first_map, nullable_map),\n            beta_nullable,\n            first_map,\n            nullable_map,\n        )\n',
        "new": '    if typ in ("repeat", "plus"):\n        return False\n',
        "test": "tests/languages/c4/test_c4_index_expr.py",
    },
    {
        "why": "语言包保真 harness 的 renderer **必须接 `line_comment_starts`**（与 pipeline 同口径），"
               "否则 harness 面对的不是用户路径、看不见「行注释吃同行元素」这类缺陷。把接线去掉 ⇒ "
               "新增的接线门禁必红（同一形态在裸接线下丢 `}` 与 `;`）",
        "file": "tests/languages/c/test_c_render_fidelity.py",
        "old": "        rules_dir=_RULES, line_comment_starts=lexer.line_terminating_comment_starts()\n",
        "new": "        rules_dir=_RULES\n",
        "test": "tests/languages/c/test_c_render_fidelity.py",
    },
    {
        "why": "`tpc check` 的共享渲染器曾漏传行终止型注释词表（与 pipeline 同形的接线漏了参数）："
               "渲染**子树**时行注释把同行后续元素吃进注释文本 ⇒ 精化产物文本静默丢 token"
               "（`param_default` = `'4 // note + 2'` 而非 `'4 + 2 // note'`；`param_override` "
               "= `'4 // c * 4'`）。本变异证明新判据真的握着那行接线",
        "file": "analyzer/shared_components.py",
        "old": "                line_comment_starts=lexer.line_terminating_comment_starts(),\n",
        "new": "",
        "test": "tests/engine/analyzer/test_shared_components_wiring.py",
    },
    {
        "why": "linter 的「候选是否收敛」判定必须**先按上下文过滤候选**（排除容器成员专用语句，"
               "如 C 的 `StructMember`）：去掉过滤 ⇒ `typedef int myint; myint v;` 这类无歧义位点"
               "被伪候选判成 `ambiguous_full_match` ⇒ 内部 warning 假报（P2a 判据必红）",
        "file": "linter/lookahead.py",
        "old": "        return name not in self._member_only\n",
        "new": "        return True  # 变异：去掉上下文候选过滤\n",
        "test": "tests/engine/linter/test_linter_lookahead.py",
    },
    {
        "why": "C 符号收集（P1）的标签命名空间来自规则声明的 `name_attr`：把 `StructSpecifier` 的"
               "属性名写坏 ⇒ `struct` 标签记录消失（kind=tag 档必红）；证明这条路确实由声明面"
               "驱动，而不是引擎侧猜规则名",
        "file": "grammar/c/02_types.toml",
        "old": "[StructSpecifier.analyzer.c_symbol_collect]\nsite = \"named\"\nname_attr = \"tag\"\n",
        "new": "[StructSpecifier.analyzer.c_symbol_collect]\nsite = \"named\"\nname_attr = \"tag_typo\"\n",
        "test": "tests/languages/c/test_c_symbol_collection.py",
    },
    {
        "why": "预扫描的 `fallback` 开关（默认 true）必须被真正消费：写成无条件建兜底正则 ⇒ "
               "声明 `fallback = false` 的包（C）重新带上 `int: typedef` 这类**非声明名**杂质，"
               "按 `phase` 对比/据名判定的消费方被污染（新判据必红）",
        "file": "lexer/pre_scan.py",
        "old": "    fallback = re.compile(rf\"\\b({all_kws})\\s+(\\w+)\") if (use_fallback and all_kws) else None\n",
        "new": "    fallback = re.compile(rf\"\\b({all_kws})\\s+(\\w+)\") if all_kws else None\n",
        "test": "tests/engine/lexer/test_pre_scan_fallback.py",
    },
    {
        "why": "raw 资格判定（P3b-M1）的**替换式试解析**是「该句唯一问题是符号歧义」的唯一证据："
               "去掉它（`eligible` 恒真）⇒ 语句级 raw 又会吞掉同句无关真错（上一轮被独立审计证伪的"
               "那一类）⇒ 反例集判据必红",
        "file": "linter/lookahead.py",
        "old": "            eligible = eligible or bool(ev[\"trial_ok\"])\n",
        "new": "            eligible = True  # 变异：去掉替换式试解析\n",
        "test": "tests/engine/linter/test_linter_raw_eligibility.py",
    },
    {
        "why": "**深度守卫**（`decl_depth <= use_depth`）是关掉「块内 typedef 出块后使用」这类作用域"
               "反例的那一层：去掉它 ⇒ `void f(void){ typedef int t; }\\nx = (t)y;` 变成 eligible，"
               "真错被静默（审计 A 类）⇒ 判据必红",
        "file": "linter/lookahead.py",
        "old": "            if position_ok and scope_ok:\n",
        "new": "            if position_ok:  # 变异：去掉深度守卫\n",
        "test": "tests/engine/linter/test_linter_raw_eligibility.py",
    },
    {
        "why": "资格判定只认**包声明的 typedef 命名空间**（`type_name` kind）：去掉 kind 过滤 ⇒ tag 名"
               "（`struct t{}` 后的 `(t)y`）也被标成符号相关（标记级判据必红；静默由 `trial_as` "
               "必要性这道第二层护栏独立顶住）",
        "file": "linter/lookahead.py",
        "old": "                if rec.get(\"kind\") not in self._type_name_kinds:\n",
        "new": "                if False:  # 变异：不按 kind 过滤\n",
        "test": "tests/engine/linter/test_linter_raw_eligibility.py",
    },
    {
        "why": "raw 兜底接入点被禁（`parse_call` 里的 `_try_raw_at_statement_start`）⇒ production 层"
               "语句位不再产出 raw 节点：本批用户可见能力整体消失（契约测试必红）",
        "file": "parser/_production.py",
        "old": "        raw_node = self._try_raw_at_statement_start(context)\n",
        "new": "        raw_node = None  # 变异：禁 raw 兜底\n",
        "test": "tests/engine/parser/test_parser_raw_site.py",
    },
    {
        "why": "`marker_matches` 退回**只按节点名**判（P1 的生产缺陷原形态）⇒ normalize 后 token 变字符串、"
               "命中恒 False ⇒ typedef 全被收成 variable ⇒ P4 误拒合法 `(t)y`（引擎侧 + 生产口径判据必红）。"
               "循环 #8 把该判据从 C 包上移至 `core/define.py`，锚点随之换家",
        "file": "core/define.py",
        "old": "    for prefix in _MARKER_TOKEN_PREFIXES:\n        if text.startswith(prefix):\n            short = text[len(prefix) :]\n            return _marker_named_hit(node, text) or _marker_scalar_hit(node, short)\n    return _marker_named_hit(node, text)\n",
        "new": "    return _marker_named_hit(node, text)  # 变异：退化只按节点名判\n",
        "test": "tests/engine/core/test_marker_matches.py",
    },
    {
        "why": "改树段（`c.raw_promote`）不再提升 ⇒ raw 段停留在占位、**没有确定结构**（P4 理解路径的"
               "结构面整体消失；判据 1 必红）",
        "file": "grammar/c/plugins/semantics/_raw_transform.py",
        "old": "            node.add_attr(CHILDREN_FIELD, [candidate])\n",
        "new": "            continue  # 变异：不提升\n",
        "test": "tests/languages/c/test_c_raw_understanding.py",
    },
    {
        "why": "理解段不再做结构选定 ⇒ 结论 `ok=False` ⇒ 改树段无据可依、不提升（P4 理解路径的"
               "**理解面**整体失效；判据 1 必红）",
        "file": "grammar/c/plugins/semantics/_raw_understand.py",
        "old": "        structure, type_text = _select_structure(candidate, names)\n",
        "new": "        structure, type_text = \"\", \"\"  # 变异：不做结构选定\n",
        "test": "tests/engine/analyzer/test_p4_raw_understanding.py",
    },
    {
        "why": "CSC001 丢掉**例外表**（退化为朴素计数）⇒ 合法共现形态被误报（`static _Thread_local` / "
               "`extern _Thread_local` / `static thread_local`），handler 单元判据同时红",
        "file": "grammar/c/plugins/checks/storage_class/rules/_storage_check.py",
        "old": "        if len(counted) > 1 and frozenset(counted) not in _ALLOWED_PAIRS:\n",
        "new": "        if len(counted) > 1:  # 变异：朴素计数（丢例外表）\n",
        "test": "tests/languages/c/test_c_storage_class_checks.py",
    },
    {
        "why": "丢掉**按声明去重** ⇒ 多声明符声明（`static extern int a, b;`）重复报（一条声明报多次）",
        "file": "grammar/c/plugins/checks/storage_class/rules/_storage_check.py",
        "old": "    if key in seen:\n        return False\n",
        "new": "    if False:  # 变异：不去重\n        return False\n",
        "test": "tests/languages/c/test_c_storage_class_checks.py",
    },
    {
        "why": "TAG001 丢掉**双方都带体**条件 ⇒ naive 判定把\"同作用域同 tag ≥2 次\"全报（实测语料一次"
               "误报 24 条无体引用：`ring` 出现 10 次、9 次是 `struct ring *`）",
        "file": "grammar/c/plugins/checks/type_semantics/rules/_tag_check.py",
        "old": "        if not (_has_body(symbol) and _has_body(prev)):\n",
        "new": "        if False:  # 变异：不看双方带体\n",
        "test": "tests/languages/c/test_c_type_semantics_checks.py",
    },
    {
        "why": "丢掉**同作用域限定**（改看父作用域）⇒ 内层同名 tag 与跨作用域同名枚举常量被误报",
        "file": "grammar/c/plugins/checks/type_semantics/rules/_tag_check.py",
        "old": "    prev = getattr(scope, \"symbols\", {}).get(symbol.name)\n",
        "new": "    prev = getattr(getattr(scope, \"parent\", None), \"symbols\", {}).get(symbol.name)  # 变异：只看父作用域\n",
        "test": "tests/languages/c/test_c_type_semantics_checks.py",
    },
    {
        "why": "LAB003 丢掉\"**只在 switch 内**\"判据 ⇒ 语料 `ring_buffer.c` 的 CaseLabel 2 + DefaultLabel 1 "
               "全部被误报为\"switch 之外的 case/default\"",
        "file": "grammar/c/plugins/checks/labels/rules/_label_check.py",
        "old": "        elif name in (CASE_NODE, DEFAULT_NODE) and not inside_switch:\n",
        "new": "        elif name in (CASE_NODE, DEFAULT_NODE):  # 变异：不看是否在 switch 内\n",
        "test": "tests/languages/c/test_c_label_checks.py",
    },
    {
        "why": "LAB001 的重复判定空转 ⇒ 同函数内重复 label **漏报**（负样本与语料判据同时红）",
        "file": "grammar/c/plugins/checks/labels/rules/_label_check.py",
        "old": "        for label, nodes in labels.items():\n",
        "new": "        for label, nodes in {}.items():  # 变异：不判重复 label\n",
        "test": "tests/languages/c/test_c_label_checks.py",
    },
    {
        "why": "派生视图去掉**FuncDef 归父作用域** ⇒ 函数定义符号与它的声明**不再同为文件域**"
               "（S2 场景 `void f(void); static void f(void){}` 判不出冲突 ⇒ 漏报）",
        "file": "grammar/c/plugins/semantics/_api.py",
        "old": "    if getattr(node, \"node_name\", None) == FUNC_DEF_NODE:\n        parent = getattr(scope, \"parent\", None)\n",
        "new": "    if getattr(node, \"node_name\", None) == FUNC_DEF_NODE:\n        parent = None  # 变异：不归父作用域\n",
        "test": "tests/languages/c/test_c_declaration_view.py",
    },
    {
        "why": "派生视图去掉**形参排除** ⇒ 原型形参被当文件域声明（`static int x; void f(int x);` 误报）",
        "file": "grammar/c/plugins/semantics/_api.py",
        "old": "    if getattr(node, \"node_name\", None) == PARAM_DECL_NODE:\n",
        "new": "    if False:  # 变异：不排除形参位\n",
        "test": "tests/languages/c/test_c_declaration_view.py",
    },
    {
        "why": "A1 丢 **hideset** 抑制 ⇒ 自引用/互递归宏再次展开（`#define x x` 不收敛，只剩预算截断兜底）",
        "file": "preprocessor/macro_expand.py",
        "old": "        if tok.masked or not prefixed or name in tok.hide or name not in macro_defs:\n",
        "new": "        if tok.masked or not prefixed or name not in macro_defs:  # 变异：丢 hideset\n",
        "test": "tests/engine/preprocessor/test_macro_expand.py",
    },
    {
        "why": "A1 丢**调用前缀判定** ⇒ 前缀语言（verilog）宏体里的裸同名标识符被当调用展开（实测 2/144）",
        "file": "preprocessor/macro_expand.py",
        "old": "        prefixed = prefix == \"\" or (\n            i > 0 and work[i - 1].text == prefix and _is_ident(tok)\n        )\n",
        "new": "        prefixed = True  # 变异：不判前缀\n",
        "test": "tests/engine/preprocessor/test_macro_expand.py",
    },
    {
        "why": "A1 丢 `call_shape` **单元素=显式无前缀** ⇒ C 的裸标识符调用形态无法声明（永不匹配）",
        "file": "preprocessor/macro_shape.py",
        "old": "    if feat.get(\"type\") == \"token\":\n",
        "new": "    if False:  # 变异：不支持单元素无前缀\n",
        "test": "tests/engine/preprocessor/test_macro_call_shape.py",
    },
    {
        "why": "A1 `##` **先展开再粘贴**（丢\"未展开拼写\"）⇒ 试金石 `CAT(EMPTY,x)` 得 `x` 而非 `EMPTYx`",
        "file": "preprocessor/macro_expand.py",
        "old": "            if _adjacent_paste(toks, i, ops.paste):\n",
        "new": "            if False:  # 变异：先展开再粘贴\n",
        "test": "tests/engine/preprocessor/test_macro_stringize_paste.py",
    },
    {
        "why": "A1 `#` 字符串化**不折叠 token 间空白** ⇒ `S(a   b)` 得 `\"a   b\"`（GCC 为 `\"a b\"`）",
        "file": "preprocessor/macro_expand.py",
        "old": "        if ch.isspace():\n            had_space = True\n",
        "new": "        if False:  # 变异：不折叠内部空白\n            had_space = True\n",
        "test": "tests/engine/preprocessor/test_macro_stringize_paste.py",
    },
    {
        "why": "A1 去掉**变参绑定** ⇒ `__VA_ARGS__` 不替换（`F(1)` 失去\"保留宏体逗号\"的 `f(1, )`）",
        "file": "preprocessor/macro_expand.py",
        "old": "        if variadic_name is not None and _is_ident(t) and t.text == variadic_name:\n",
        "new": "        if False:  # 变异：不支持变参\n",
        "test": "tests/engine/preprocessor/test_macro_stringize_paste.py",
    },
    {
        "why": "A1 丢**调用点掩码过滤** ⇒ 匹配不看是否落在字面量/注释内（`printf(\"FOO\")` 被展开）",
        "file": "preprocessor/_expand.py",
        "old": "        if _masked(m.start()):\n            continue  # 掩码区内（字面量/注释）不展开\n",
        "new": "        if False:  # 变异：不看掩码\n            continue\n",
        "test": "tests/engine/preprocessor/test_macro_mask.py",
    },
    {
        "why": "A1 形参表未闭合**退回容错退化**（静默当对象宏）⇒ 配置错误不 fail-fast（作者裁定项）",
        "file": "preprocessor/primitives/define.py",
        "old": "        if matched is None:\n            raise ConfigError(\n",
        "new": "        if matched is None:  # 变异：容错退化（不报错）\n            return\n        if False:\n            raise ConfigError(\n",
        "test": "tests/engine/preprocessor/test_primitives.py",
    },
    {
        # ── 以下 4 条：**端到端**变异（A1 返工后新增；来源 = 独立审计 15 反例）──
        # 教训：上一轮 8 条 A1 变异全打在内部函数上，端到端 10 项错而全绿 ⇒ 变异必须
        # 打"用户看得见的路径"（命中 tests/.../test_c_macro_end_to_end.py）。
        "why": "`#` 字符串化若不用实参原文，`V(a ,  b)` 会丢掉逗号后的空白"
               "（审计 P1-1；GCC 为 \"a , b\"）——端到端可见",
        "file": "preprocessor/macro_expand.py",
        "old": "                raw = (\n"
               "                    raw_variadic\n"
               "                    if raw_variadic is not None\n"
               "                    else sep.join(join(a) for a in variadic)\n"
               "                )\n",
        "new": "                raw = sep.join(join(a) for a in variadic)  "
               "# 变异：丢原文切片\n",
        "test": "tests/engine/preprocessor/test_c_macro_end_to_end.py",
    },
    {
        "why": "跨行块注释的续行没有起始定界符，逐行重算掩码 ⇒ 续行内的宏名被误当"
               "调用展开（审计 P1-3，真实语料 edge_comments.c）",
        "file": "preprocessor/_expand.py",
        "old": "        macro_matches = _collect_macro_matches(ctx, line, line_masks[line_no - 1])\n",
        "new": "        macro_matches = _collect_macro_matches(ctx, line)  "
               "# 变异：退回逐行掩码\n",
        "test": "tests/engine/preprocessor/test_c_macro_end_to_end.py",
    },
    {
        "why": "tokenize 不掩码 ⇒ 字符串/注释里的逗号与括号被当实参分隔符/收束符"
               "（审计 P0-3/P0-4），宏体里的字面量也会被当可展开文本"
               "（Lead 独立审计的真 bug：`#define B \"A\"`）",
        "file": "preprocessor/macro_expand.py",
        "old": "    ops = operators\n"
               "    masks = mask_spans(\n"
               "        text,\n"
               "        ops.string_delimiters if ops else (),\n"
               "        ops.escape if ops else None,\n"
               "        syntax,\n"
               "    )\n"
               "    return tokenize(text, ops, masks)\n",
        "new": "    ops = operators\n"
               "    return tokenize(text, ops, None)  # 变异：不掩码\n",
        "test": "tests/engine/preprocessor/test_c_macro_end_to_end.py",
    },
    {
        "why": "裸调用正则若不按名字长度降序交替，短宏名会吃掉长宏名前缀"
               "（`#define A 1` + `#define AB 2` ⇒ `AB` 不展开；审计 P0-5）",
        "file": "preprocessor/_expand.py",
        "old": "        names = sorted({n for n in macro_names if n}, "
               "key=len, reverse=True)\n",
        "new": "        names = sorted({n for n in macro_names if n})  "
               "# 变异：字典序（短名吃长名前缀）\n",
        "test": "tests/engine/preprocessor/test_c_macro_end_to_end.py",
    },
    {
        # ── A2 ①：默认口径统一（gap ⑬ 事故：CLI 默认 True / 库默认 False 分叉）──
        "why": "项目配置把 `expand_macros` 改回 false ⇒ **库默认路径**不预处理：合法 `#define` 报 "
               "`parse truncated`，与 CLI 默认（True）分叉（gap ⑬ 事故）",
        "file": "config/tpc_config.json",
        "old": '        "expand_macros": true,',
        "new": '        "expand_macros": false,',
        "test": "tests/engine/pipeline/test_expand_macros_default.py",
    },
    {
        "why": "`_DEFAULT_SPECS` 兜底若回退 False，wheel 安装（无项目配置）会与 CLI 默认分叉"
               "（gap ⑬ 事故的第二个侧面）",
        "file": "pipeline/__init__.py",
        "old": '    ("expand_macros", "expand_macros", True),',
        "new": '    ("expand_macros", "expand_macros", False),',
        "test": "tests/engine/pipeline/test_expand_macros_default.py",
    },
]


def _ensure_clean_tree() -> bool:
    """要求工作区干净——变异会临时改源码，脏树下还原会掩盖未提交改动。"""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        print("[error] 无法读取 git 状态（不是 git 仓库？）")
        return False
    dirty = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if dirty:
        print("[error] 工作区不干净，拒绝施加变异（会掩盖未提交改动）：")
        for ln in dirty[:10]:
            print(f"    {ln}")
        print("    先提交或 stash，再跑本工具。")
        return False
    return True


def _run_mutation(m: dict[str, str]) -> tuple[bool, str]:
    """施加变异 → 跑测试 → 还原。返回 (门禁是否如期变红, 说明)。

    ⚠ 读写都用 `newline=""`：本工具会临时改写版本库里的源码，而本仓的 `.gitattributes`
    约定索引与工作区**一律 LF**——Python 在 Windows 上按默认 newline 写回会把 LF 翻成
    CRLF（`git status` 随后把这 20+ 个文件报成"已修改"、破坏行尾统一）。读写都不翻译，
    还原就是逐字节原样。
    """
    path = os.path.join(_ROOT, m["file"])
    if not os.path.isfile(path):
        return False, f"文件不存在（清单过时？）：{m['file']}"
    with open(path, encoding="utf-8", newline="") as f:
        original = f.read()
    if m["old"] not in original:
        return False, (
            f"变异锚点未找到（源码已变，清单过时）：{m['file']}\n"
            f"      期望锚点：{m['old'].splitlines()[0][:70]}…"
        )
    if original.count(m["old"]) > 1:
        return False, f"变异锚点不唯一（{original.count(m['old'])} 处）：{m['file']}"

    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(original.replace(m["old"], m["new"], 1))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", m["test"], "-q", "-n", "0", "--no-header"],
            cwd=_ROOT, capture_output=True, text=True, encoding="utf-8",
        )
    finally:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(original)
        with open(path, encoding="utf-8", newline="") as f:
            assert f.read() == original, f"还原失败，请手动检查 {m['file']}"

    if proc.returncode != 0:
        return True, "测试如期变红 ✓"
    return False, (
        "测试**仍然通过** ✗ —— 门禁可能已失效，或被削弱的测试掩盖了变异"
    )


def _print_mutation_list() -> None:
    """`--list`：逐条打印变异清单（文件 / 变异 / 期望变红的测试 / 来源事故）。

    ⚠ 有几条变异是**纯删除**（`new` 为空串，如"删掉那行注入声明"）——
    `"".splitlines()` 是空列表，直接取 `[0]` 会 IndexError（2026-09-26 修）。
    """
    for i, m in enumerate(_MUTATIONS, 1):
        old_head = (m["old"].splitlines() or [""])[0][:70]
        new_head = (m["new"].splitlines() or [""])[0][:50] or "（删除该锚点）"
        print(f"{i}. {m['file']}")
        print(f"   变异：{old_head}… → {new_head}…")
        print(f"   期望变红：{m['test']}")
        print(f"   来源事故：{m['why']}")


def _select_mutations(only: int | None) -> list[tuple[int, dict]] | None:
    """选中要跑的变异（`--only` 指定单条）；编号不存在 → None（调用方退 2）。"""
    selected = list(enumerate(_MUTATIONS, 1))
    if only is None:
        return selected
    picked = [(i, m) for i, m in selected if i == only]
    if not picked:
        print(f"[error] 无第 {only} 条")
        return None
    return picked


def _run_mutations(selected: list[tuple[int, dict]]) -> list[str]:
    """逐条跑变异 → 未如期变红者清单（调用方据此定退出码）。"""
    failures: list[str] = []
    print(f"[info] 抽查 {len(selected)} 条变异（每条跑一次相关测试，约一分钟）\n")
    for i, m in selected:
        print(f"[{i}/{len(_MUTATIONS)}] {m['file']}")
        ok, note = _run_mutation(m)
        print(f"        {note}")
        if not ok:
            failures.append(f"{m['file']}（期望 {m['test']} 变红）：{note}")
    print()
    return failures


def main() -> int:
    """门禁有效性抽查（变异法）CLI 入口。"""
    ap = argparse.ArgumentParser(description="门禁有效性抽查（变异）")
    ap.add_argument("--list", action="store_true", help="只列清单")
    ap.add_argument("--only", type=int, default=None, help="只跑第 N 条（从 1 起）")
    args = ap.parse_args()

    if args.list:
        _print_mutation_list()
        return 0

    if not _ensure_clean_tree():
        return 2

    selected = _select_mutations(args.only)
    if selected is None:
        return 2

    failures = _run_mutations(selected)
    if failures:
        print("[FAIL] 以下变异未如期触发门禁：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] 全部变异都如期变红——这些门禁仍然握着它们该握的东西")
    return 0


if __name__ == "__main__":
    sys.exit(main())
