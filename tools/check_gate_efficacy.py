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
            # 块规则（有 block_end）或括号定界语句容器（如 CompoundStmt
            # `{ @Stmt* }`）：转块分支注册节点并递归 body。
            if info.get("block_end") or _is_bracket_stmt_container(
                self, candidates[0], t.type
            ):
                return self._discover_block(
                    tokens, i, end, context, depth, nodes, record=record
                )
""",
        "new": """        if candidates and isinstance(candidates[0], str):
            info = self._tree.get(candidates[0], {}) or {}
            if False:  # 变异：不转块分支
                return self._discover_block(
                    tokens, i, end, context, depth, nodes, record=record
                )
""",
        "test": "tests/languages/c4/test_c4_linter.py",
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
               "不再进 Stmt 交替——本变异证明那三条块作用域用例真的握着这行声明"
               "（同一条声明还管成员表位，两条通路都在 tests/languages/c/test_c_standard_conformance.py）",
        "file": "grammar/c/plugins/c23/10_static_assert_alias.toml",
        "old": '[StaticAssertC23Decl.inject]\ntargets = ["@Stmt", "@StructMemberExtra"]\n',
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
        "why": "C 符号收集（P1）的标签命名空间来自规则声明的 `name_attr`：把 `StructSpecifier` 的"
               "属性名写坏 ⇒ `struct` 标签记录消失（kind=tag 档必红）；证明这条路确实由声明面"
               "驱动，而不是引擎侧猜规则名",
        "file": "grammar/c/02_types.toml",
        "old": "[StructSpecifier.analyzer.c_symbol_collect]\nsite = \"named\"\nname_attr = \"tag\"\n",
        "new": "[StructSpecifier.analyzer.c_symbol_collect]\nsite = \"named\"\nname_attr = \"tag_typo\"\n",
        "test": "tests/languages/c/test_c_symbol_collection.py",
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
        "old": "        macro_matches = _collect_macro_matches(\n"
               "            ctx, line, line_masks[line_no - 1], line_no\n"
               "        )\n",
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
    {
        "why": "指令 marker 序号源若各起一份（嵌套 include 递归不共享计数器）⇒ 嵌套文件与宿主"
               "撞号，`restore_anchors` 按 marker 唯一性还原会错位（2026-10-17 实测）",
        "file": "preprocessor/_expand.py",
        "old": "    seq_box = ctx[\"_seq_box\"]\n"
               "    seq = seq_box[0]\n"
               "    seq_box[0] = seq + 1\n",
        "new": "    seq_box = [0]  # 变异：序号源各起一份（嵌套撞号）\n"
               "    seq = seq_box[0]\n"
               "    seq_box[0] = seq + 1\n",
        "test": "tests/engine/preprocessor/test_primitives.py",
    },
    {
        # ── A2 ②：#include 真实实现的三个关键行为 ──
        "why": "渲染前剪枝若被跳过，include 内容会**内联**进格式化输出（保真破坏 + 不幂等）",
        "file": "pipeline/__init__.py",
        "old": "    if not regions or ast is None:\n"
               "        return ast\n"
               "    offsets = _token_offsets(ctx.source, tokens)\n",
        "new": "    if True:  # 变异：不剪枝（内联 include 内容）\n"
               "        return ast\n"
               "    offsets = _token_offsets(ctx.source, tokens)\n",
        "test": "tests/engine/preprocessor/test_c_include_e2e.py",
    },
    {
        "why": "`on_missing` 策略失效 ⇒ C 包缺头文件退回打印/静默，用户看不到受控诊断",
        "file": "preprocessor/primitives/include.py",
        "old": '    if cfg.get("on_missing") == "error":\n',
        "new": "    if False:  # 变异：策略失效（始终 warn）\n",
        "test": "tests/engine/preprocessor/test_c_include_e2e.py",
    },
    {
        "why": "`max_depth` 检查失效 ⇒ 病态包含链不再给 `depth` 诊断（无限递归风险）",
        "file": "preprocessor/primitives/include.py",
        "old": '    if max_depth is not None and len(ctx["_include_stack"]) >= int(max_depth):\n',
        "new": "    if False:  # 变异：不检深度\n",
        "test": "tests/engine/preprocessor/test_c_include_e2e.py",
    },
    {
        # ── A2 ④：宏定义形式语法检查（linter，AST 前） ──
        "why": "宏形式语法检查若未被 linter 接线（scanner 不产出）⇒ 畸形 `#define` 重新静默，"
               "形式化语法错误不再由 linter 报出（用户面无诊断）",
        "file": "linter/scanner.py",
        "old": "        errors = macro_syntax_diagnostics(source, self._rules_dir)\n",
        "new": "        errors = []  # 变异：不接宏形式语法检查\n",
        "test": "tests/engine/linter/test_macro_syntax_checks.py",
    },
    {
        # ── A2 ④ 续：检查启用改为**语言包声明驱动**（作者提示"需要对应的宏语法配置"）──
        "why": "`[macro_syntax]` 未声明的语言包也被按'启用'处理（声明面被忽略）⇒ verilog 的宏定义语法"
               "（形参项形式不同）被套上 C 的约束、合法定义误报",
        "file": "preprocessor/macro_shape.py",
        "old": "    raw = cfg.get(MACRO_SYNTAX_KEY)\n"
               "    if raw is None:\n"
               "        return None\n",
        "new": "    raw = cfg.get(MACRO_SYNTAX_KEY) or {}  # 变异：未声明也当启用\n"
               "    if raw is None:\n"
               "        return None\n",
        "test": "tests/engine/linter/test_macro_syntax_checks.py",
    },
    {
        # ── 阶段 4 首片 B：`#if` / `#elif` 整型常量表达式求值 ──
        "why": "`#if` 求值真值判据若写反（`value != 0` → `value == 0`）⇒ 条件分支全反，"
               "活跃分支/解析面与条件文本不符（C 端到端取错分支）",
        "file": "preprocessor/condition.py",
        "old": "    return value != 0, diags\n",
        "new": "    return value == 0, diags  # 变异：真值判据取反\n",
        "test": "tests/engine/preprocessor/test_c_conditionals.py",
    },
    {
        "why": "inactive 外层里的 `#if` 若仍求值 ⇒ 被跳过组内出现本不该有的表达式诊断"
               "（C99：被跳过组不求值、不报表达式错；gcc 实测静默）",
        "file": "preprocessor/primitives/condition.py",
        "old": "    if outer_active(ctx):\n"
               "        active, diags = _eval_arg(stripped, prefix, ctx, syn)\n",
        "new": "    if True:  # 变异：inactive 外层也求值\n"
               "        active, diags = _eval_arg(stripped, prefix, ctx, syn)\n",
        "test": "tests/engine/preprocessor/test_c_conditionals.py",
    },
    {
        "why": "已选中分支后的 `#elif` 若仍求值 ⇒ 未被采用的 elif 表达式错误也报"
               "（C99：前支已选中时 elif 不求值；gcc `#elif 1/0` 静默）",
        "file": "preprocessor/primitives/condition.py",
        "old": "    if not already and outer:\n"
               "        active, diags = _eval_arg(stripped, prefix, ctx, syn)\n",
        "new": "    if outer:  # 变异：已选中分支后的 elif 也求值\n"
               "        active, diags = _eval_arg(stripped, prefix, ctx, syn)\n",
        "test": "tests/engine/preprocessor/test_c_conditionals.py",
    },
    {
        "why": "扫描结束不报未闭合条件块 ⇒ 缺 `#endif` 的输入静默（C 标准要求诊断；"
               "gcc: unterminated #if）",
        "file": "preprocessor/_expand.py",
        "old": "    for frame in ctx.get(\"_ifdef_stack\", []):\n"
               "        block = frame[\"block\"]\n",
        "new": "    for frame in []:  # 变异：不报未闭合条件块\n"
               "        block = frame[\"block\"]\n",
        "test": "tests/engine/preprocessor/test_c_conditionals.py",
    },
    {
        "why": "条件求值的宏表若不是**扫描到该行时的活值**（漏并源码 `#define`）⇒ 后文才定义的宏"
               "在后文 `#if` 里仍被当 0（顺序语义错）",
        "file": "preprocessor/condition.py",
        "old": "    defs.update(ctx.get(\"macro_defs\") or {})\n    return defs\n",
        "new": "    return defs  # 变异：只用 -D/-U，漏并源码宏表\n",
        "test": "tests/engine/preprocessor/test_c_conditionals.py",
    },
    {
        # ── A2 ①：宏实参个数检查（插件侧 check 族）──
        "why": "展开期不记录函数宏调用点事实 ⇒ 实参个数检查失去输入（`tpc check` 对"
               "少给/多给重新静默）",
        "file": "preprocessor/_expand.py",
        "old": "        if is_func and ctx.invocations is not None:\n"
               "            ctx.invocations.append(\n",
        "new": "        if False and ctx.invocations is not None:  # 变异：不记调用点事实\n"
               "            ctx.invocations.append(\n",
        "test": "tests/engine/preprocessor/test_macro_call_sites.py",
    },
    {
        "why": "解析失败文件一律跳过语义阶段（不跑 `ast_optional` postpass）⇒ 实参不足"
               "（展开成非法语法的那批文件）的 arity 诊断全部丢失",
        "file": "analyzer/checker.py",
        "old": "        if fr.ast is None and not _has_ast_optional_postpass():\n"
               "            return\n",
        "new": "        if fr.ast is None:  # 变异：解析失败一律跳过事实型 postpass\n"
               "            return\n",
        "test": "tests/languages/c/test_c_macro_args_checks.py",
    },
    {
        "why": "零形参宏若不判（`Z()` 合法默认吞掉一切）⇒ `Z(2)` 这类传参给零形参宏的"
               "硬错被漏报（GCC 全档报 'passed 1 arguments, but takes just 0'）",
        "file": "grammar/c/plugins/checks/macro_args/rules/_macro_args_check.py",
        "old": "    if n == 0:\n"
               "        # 零形参宏的合法调用只有 `Z()`（空实参列表；注释算空）\n"
               "        if slots == 1 and bool(inv.get(\"single_empty\")):\n"
               "            return None\n"
               "        return \"0\", slots\n",
        "new": "    if n == 0:\n"
               "        return None  # 变异：零形参宏不判\n",
        "test": "tests/languages/c/test_c_macro_args_checks.py",
    },
    {
        "why": "合成节点的位置（已是原始源坐标）若再经'展开坐标→原始源'行表回源 ⇒ 行号二次"
               "错位（`#if` 块压缩后的宏调用诊断指到错行）",
        "file": "analyzer/diag_serialize.py",
        "old": "        if same_file and not original:\n"
               "            line0 = map_diag_line(fr, line0)\n",
        "new": "        if same_file:  # 变异：原始坐标也经行表回源\n"
               "            line0 = map_diag_line(fr, line0)\n",
        "test": "tests/engine/analyzer/test_diag_line_map.py",
    },
    {
        "why": "调用点事实若不按**宏定义时间线**过滤（用展开器的最终宏表）⇒ 后置定义 / 重定义"
               "前的合法调用点被误判成宏调用（`int F(int);` 之后才 `#define F(a,b)` 的合法 C 报 arity 错）",
        "file": "preprocessor/_expand.py",
        "old": "        if macro_events:\n",
        "new": "        if False:  # 变异：不按定义时间线过滤\n",
        "test": "tests/languages/c/test_c_macro_args_checks.py",
    },
    {
        "why": "`tpc check` 语法阶段若不查**原始源**宏定义形式语法 ⇒ 定义行被扫指令消费后"
               "展开文本里看不到它们，`tpc lint` 报的宏形式错在 check 里重新静默（两路径分叉）",
        "file": "analyzer/structure.py",
        "old": "        raw_macro_diags = raw_source_macro_diags(raw_source, self._ctx.rules_dir)\n",
        "new": "        raw_macro_diags = []  # 变异：不查原始源宏语法面\n",
        "test": "tests/languages/c/test_c_macro_syntax_check_path.py",
    },
    {
        "why": "接缝重扫若失效（替换文本末尾的函数宏名不再与源码后续 `(...)` 合成调用）⇒ "
               "`#define g f` + `g(2)` 停在 `f(2)`、`f(2)(9)` 停在 `2*g(9)`（C99 §6.10.3.4 "
               "替换列表连同其余源码重扫描缺失；verilog 前缀接缝同）",
        "file": "preprocessor/_expand.py",
        "old": "    budget = int(_get_expand_config().get(\"max_iterations\", 128))\n",
        "new": "    return body_toks, end  # 变异：禁接缝重扫\n",
        "test": "tests/engine/preprocessor/test_macro_rescan.py",
    },
    {
        "why": "接缝处的 hideset 若不取**交集**（名字 token ∩ 实参/闭括号 token）⇒ 互递归"
               "别名 `f(2)(9)` 停在 `2*f(9)`（GCC `2*9*g`）——实参来自源码、hide 为空，"
               "交集才能让名字 token 的 hide 不传给替换文本",
        "file": "preprocessor/_expand.py",
        "old": "        hideset = cand.hide\n"
               "        for arg in args:\n"
               "            for t in arg:\n"
               "                hideset = hideset & t.hide\n"
               "        hideset = hideset & rest_toks[after - 1].hide\n",
        "new": "        hideset = cand.hide  # 变异：接缝 hideset 不取交集\n",
        "test": "tests/engine/preprocessor/test_macro_rescan.py",
    },
    {
        "why": "跨行实参收集若失效（单行未闭合就放弃）⇒ `F(1,` + 下一行 `2)` 保持原样、"
               "名字-括号跨行不展开（C 预处理 token 不区分换行；GCC 会展开）",
        "file": "preprocessor/_expand.py",
        "old": "    joined = suffix\n    segs = [suffix]\n",
        "new": "    return None  # 变异：不支持跨行实参收集\n    joined = suffix\n"
               "    segs = [suffix]\n",
        "test": "tests/engine/preprocessor/test_macro_multiline_call.py",
    },
    {
        "why": "混合行（同行普通宏 + 跨行调用）的区域条目若少一项（6 元组 vs 7 元组）⇒ "
               "`_apply_cross_line` 解包 ValueError：管线崩、`tpc check` 整文件回退原文"
               "（用户看到 `#define` 被当 token 的假语法错误）",
        "file": "preprocessor/_expand.py",
        "old": "            line_regions.append(\n"
               "                (col, end, name, is_func, spliced, None, None, line_no)\n"
               "            )\n",
        "new": "            line_regions.append(\n"
               "                (col, end, name, is_func, spliced, None, None)\n"
               "            )  # 变异：混合行区域元组缺一项\n",
        "test": "tests/engine/preprocessor/test_macro_multiline_call.py",
    },
    {
        "why": "include 内容行若先于指令行 marker 写入（handler 先于 marker 执行）⇒ "
               "内容行排在 `#include` 前、clean 行序/行映射/渲染回插顺序错位"
               "（A2 末片 include 顺序偏差）",
        "file": "preprocessor/_expand.py",
        "old": "        _inject_directive_marker(ctx, stack, jno, line, syntax)\n"
               "        _invoke_directive(op, stripped, prefix, directive_name, ctx)\n",
        "new": "        _invoke_directive(op, stripped, prefix, directive_name, ctx)\n"
               "        _inject_directive_marker(ctx, stack, jno, line, syntax)\n",
        "test": "tests/engine/preprocessor/test_include_order.py",
    },
    {
        "why": "跨盘路径显示若直接 `os.path.relpath`（不捕获 ValueError）⇒ Windows "
               "`C:`↔`E:` 输入时 `tpc check` 文本/HTML 报告崩溃（已实测 traceback）",
        "file": "core/utils.py",
        "old": "    try:\n"
               "        return os.path.relpath(path)\n"
               "    except ValueError:\n"
               "        return path\n",
        "new": "    return os.path.relpath(path)  # 变异：跨盘 ValueError 直接冒泡\n",
        "test": "tests/engine/core/test_safe_relpath.py",
    },
    {
        "why": "D3 若不把 blockquote 续行并入 `Impl:`/`Test:` 字段 ⇒ 续行里的悬空"
               "文件引用漏报（已删档 ADR-0017 引 `test_macro_call_node.py` 而 D3=0）",
        "file": "policy/check_doc_refs.py",
        "old": "            j = i + 1\n"
               "            while j < len(lines):\n",
        "new": "            j = i + 1\n"
               "            while False and j < len(lines):  # 变异：不扫续行\n",
        "test": "tests/policy/test_check_doc_refs.py",
    },
    {
        "why": "行终止注释在 Union 回退处就地落地（写成 branch 末尾 Text）⇒ 父级同行 "
               "`;`/`,`/声明符落进注释：C 包 enum 尾逗号 / struct / 初始化 / 带声明符"
               "形态丢 token、二遍 parse truncated（2026-10-19 修复）",
        "file": "renderer/doc.py",
        "old": "        return Union(flat_doc, broken_doc), flat_pending\n"
               "    return broken_doc, broken_pending\n",
        "new": "        return Union(flat_doc, broken_doc), flat_pending\n"
               "    return (\n"
               "        Union(\n"
               "            _append_suffix(flat_doc, \"\".join(flat_pending)),\n"
               "            _append_suffix(broken_doc, \"\".join(broken_pending)),\n"
               "        ),\n"
               "        [],\n"
               "    )\n",
        "test": "tests/engine/renderer/test_doc_line_suffix.py",
    },
    {
        "why": "InitList 产生式的尾随逗号是**独立可选元素**，若不单独绑定（只绑 items）"
               "⇒ 渲染器静默丢一个非 trivia token：`int a[] = {1, 2,};` 渲成 `{1, 2};`"
               "（判据 7 红；2026-10-19 修复，EnumBody 同形）",
        "file": "grammar/c/01_declarations.toml",
        "old": 'trailing_comma = "$3"',
        "new": '# 变异：去掉 InitList 尾随逗号绑定',
        "test": "tests/languages/c/test_c_render_fidelity.py",
    },
    {
        "why": "行中注释的 inline 通道若按残留 current_rule 判（而非节点自己的规则）"
               "⇒ 失败尝试留下的内层 inline 规则把容器内注释挂成'节点前置'：C 初始化"
               "列表 `{1, /* c */ 2}` 渲到 `{` 前、`{1, 2, /* c */ }` 双份（2026-10-19 修）",
        "file": "parser/_production.py",
        "old": "    owns_node = getattr(node, \"_rule_name\", None) == getattr(rule, \"name\", None)\n"
               "    if owns_node and getattr(rule, \"inline\", False):\n",
        "new": "    if getattr(rule, \"inline\", False):  # 变异：按残留 current_rule 判通道\n",
        "test": "tests/languages/c/test_c_initializers.py",
    },
    {
        "why": "行中注释回溯双收集若不去重（同节点同位置）⇒ 同一注释归两次："
               "C 初始化列表 `{1, 2, /* c */ }` 渲成两份（2026-10-19 修）",
        "file": "parser/_production.py",
        "old": "    seen = seen_map.setdefault(node, set())\n"
               "    if key in seen:\n"
               "        return True\n",
        "new": "    seen = seen_map.setdefault(node, set())\n"
               "    if False and key in seen:  # 变异：关掉同节点同位置去重\n"
               "        return True\n",
        "test": "tests/languages/c/test_c_initializers.py",
    },
    {
        "why": "闭括号前的行中注释若走行内锚通道 ⇒ 锚到括号前最后 token（原子节点是 "
               "`ref` 布局，定位不到）⇒ 注释静默丢：C 初始化列表 `{1, 2 /* c */ }` 整条"
               "丢失（2026-10-19 修）",
        "file": "parser/_production.py",
        "old": "        elif after is None or after.type.startswith(\"symbol\") or (\n"
               "            after.type.startswith(BRACKET_R_PREFIX)\n"
               "        ):\n",
        "new": "        elif after is None or after.type.startswith(\"symbol\"):\n",
        "test": "tests/languages/c/test_c_initializers.py",
    },
    {
        "why": "成员位空槽位注入丢失 ⇒ 合法 C11 的 `struct s { int a; _Static_assert(1, \"x\"); };` "
               "整条解析失败（C11 §6.7.2.1；空槽位是容器级分支的唯一入口，2026-10-21 补）",
        "file": "grammar/c/plugins/c11/10_static_assert.toml",
        "old": 'targets = ["@Stmt", "@StructMemberExtra"]\n',
        "new": 'targets = ["@Stmt"]  # 变异：丢成员位槽\n',
        "test": "tests/languages/c/test_c_standard_conformance.py",
    },
    {
        "why": "C23 分派器若只留两参分支 ⇒ 合法的单参 `static_assert(1);` 解析失败"
               "（C23 §6.7.10 消息可省，2026-10-21 补）",
        "file": "grammar/c/plugins/c23/10_static_assert_alias.toml",
        "old": '    "@StaticAssertC23MsgDecl|@StaticAssertC23NoMsgDecl",\n',
        "new": '    "@StaticAssertC23MsgDecl",  # 变异：丢单参分支\n',
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "字面量前缀表若被忽略（引擎只按裸定界符捕获）⇒ 合法 `u8\"x\"` / `L'x'` "
               "退化为 id + literal.string 两 token、整条声明解析失败（2026-10-21 补）",
        "file": "lexer/capture_runner.py",
        "old": '    prefixes = section.get("prefixes", {}) or {}\n',
        "new": '    prefixes = {}  # 变异：忽略前缀声明\n',
        "test": "tests/languages/c/test_c_lexer.py",
    },
    {
        "why": "C23 二进制常量靠 c_prefix 形态的 base_prefix 加分支实现；去掉 `0b` 分支 ⇒ "
               "`0b1010` 又切回 `0` + `b1010`（2026-10-21 补）",
        "file": "grammar/c/plugins/c23/_number_c23.toml",
        "old": 'base_prefix = "0x|0b"\n',
        "new": 'base_prefix = "0x"  # 变异：丢二进制分支\n',
        "test": "tests/languages/c/test_c_lexer.py",
    },
    {
        "why": "C23 数字分隔符靠引擎把声明编译成分隔态子图；关掉展开 ⇒ `1'000'000` 又切成 "
               "`1` + 字符常量 + `000`（2026-10-21 补）",
        "file": "lexer/number_gen.py",
        "old": "        if not self.digit_separator:\n            return\n",
        "new": "        if True:  # 变异：关掉分隔符展开\n            return\n",
        "test": "tests/engine/lexer/test_number_digit_separator.py",
    },
    {
        # ⚠ 反向教训：本条原写成"丢掉 `c_octal` 的分隔符声明"⇒ **测试仍绿**——因为 `0'7`
        #   的 digit 序列同时落在 `c_dec`（`digits = "any"`）里、扫描取最长 token，`c_octal`
        #   那条声明本就是重复知识（已删；见 `_number_c23.toml` 末段注）。变异改为对
        #   真正承担该职责的 `c_dec` 条目下手。
        "why": "数字分隔符的档位判别靠 c23 插件给核心 `c_dec` 按名合并 `digit_separator`；"
               "去掉该字段 ⇒ c23 档的 `1'000'000` 又切成 `1` + 字符常量 + `000`（2026-10-21 补）",
        "file": "grammar/c/plugins/c23/_number_c23.toml",
        "old": 'name = "c_dec"\nsuffix = { chars = "uUlLfFd", max = 3 }\ndigit_separator = "\'"\n',
        "new": 'name = "c_dec"\nsuffix = { chars = "uUlLfFd", max = 3 }\n# 变异：丢十进制分隔符声明\n',
        "test": "tests/languages/c/test_c_lexer.py",
    },
    {
        "why": "可选件 grammar 的档位门控若被去掉（`get_component_grammar_files` 不再看档位）"
               "⇒ C23 规则在基线档照样上膛 → `[[属性]]` 在基线档被解析、`_Static_assert(1)` "
               "这类『只由核心 token 组成』的形态又会漏进下档（ADR-0023）",
        "file": "core/plugin_loader.py",
        "old": "        if not _grammar_tier_allows(info[\"name\"]):\n            continue\n",
        "new": "        # 变异：去掉可选件 grammar 的档位过滤\n",
        "test": "tests/engine/core/test_tier_gated_grammar.py",
    },
    {
        "why": "空槽位规则若恢复成『匹配空』（而非不可匹配）⇒ 宿主的 `@Slot*` 迭代项零进展，"
               "repeat 不收敛（基线档 `@AttributeSlot*` 告警风暴 + 挂起，ADR-0023 实测）",
        "file": "parser/_production.py",
        "old": "    if not rule.prods and not getattr(rule, \"is_block\", False):\n",
        "new": "    if False:  # 变异：把空槽位当可匹配\n",
        "test": "tests/languages/c/test_c_standard_tiers.py",
    },
    {
        "why": "C23 下划线拼写单参规则若丢**成员表位**注入 ⇒ 合法 C23 代码"
               "`struct s { int a; _Static_assert(1); };` 整条解析失败（§6.7.10 消息可省对"
               "两种拼写都成立；循环 #41 补）",
        "file": "grammar/c/plugins/c23/22_static_assert_no_msg.toml",
        "old": 'targets = ["@Stmt", "@StructMemberExtra"]\n',
        "new": 'targets = ["@Stmt"]  # 变异：丢成员位槽\n',
        "test": "tests/languages/c/test_c_standard_conformance.py",
    },
    {
        "why": "c23 单参下划线拼写规则**没在插件清单里登记**（`[grammar] files` 漏一行）⇒"
               "生产路径根本加载不到它、合法 `_Static_assert(1);` 不再进 AST（循环 #41 补；"
               "判据选 conformance = 走生产路径。⚠ c23 插件测试的 helper 传 "
               "`ext_dirs=[plugins]`，那是『显式扩展目录』通道（ADR-0023 边界：不受门控），"
               "会把插件 TOML 无条件上膛 ⇒ 对本条变异不敏感，不能当判据面）",
        "file": "grammar/c/plugins/c23/tpc.toml",
        "old": '    "22_static_assert_no_msg.toml",\n',
        "new": "",
        "test": "tests/languages/c/test_c_standard_conformance.py",
    },
    {
        "why": "枚举固定底层类型的槽位若从核心宿位漏写（`EnumSpecifier` 少一个 `@EnumSpecExtra?`）"
               "⇒ C23 合法形态 `enum e : int { A };` 整条解析失败（循环 #42；槽位 = 标签后中段"
               "注入的唯一入口，同 `@AttributeSlot` 的教训）",
        "file": "grammar/c/02_types.toml",
        "old": '    "@EnumSpecExtra?",\n    "@EnumBody?",\n',
        "new": '    "@EnumBody?",  # 变异：去掉固定底层类型槽位\n',
        "test": "tests/languages/c/test_c_standard_conformance.py",
    },
    {
        "why": "C23 枚举底层类型规则若没注入槽位（丢掉 `[EnumUnderlyingType.inject]`）⇒ 槽位"
               "仍是空产生式 ⇒ 合法 `enum e : int { A };` 解析失败（循环 #42；注入点 = 核心"
               "空槽位 `@EnumSpecExtra.production[0]`，命名体/匿名体共用）",
        "file": "grammar/c/plugins/c23/23_enum_underlying.toml",
        "old": '[EnumUnderlyingType.inject]\ntargets = ["@EnumSpecExtra.production[0]"]\n',
        "new": "",
        "test": "tests/languages/c/test_c23_increment_plugin.py",
    },
    {
        "why": "ENUM003 的 C23 豁免若被去掉（`enum E : int;` 不再算完整）⇒ 合法不透明枚举声明"
               "被误报 'enum E 无枚举列表'（循环 #42；ADR-0021 行 6 的触发条件：实现固定底层"
               "类型枚举时必须加豁免）",
        "file": "grammar/c/plugins/checks/type_semantics/rules/_tag_check.py",
        "old": '        if _tag_kind(symbol) != "enum" or _has_body(symbol) or _has_complete_type(symbol):\n',
        "new": '        if _tag_kind(symbol) != "enum" or _has_body(symbol):  # 变异：去掉固定底层类型豁免\n',
        "test": "tests/languages/c/test_c_type_semantics_checks.py",
    },
    {
        "why": "说明符顺序自由（存储类/限定符 + typedef 名）靠宿主声明符位的『声明符优先』"
               "交替：去掉交替第二支 ⇒ `extern T *p;` / `const T *p` 整条解析截断"
               "（真实 C 语料 zlib/cJSON 命中；循环 #44 补）",
        "file": "grammar/c/01_declarations.toml",
        "old": '    "(@DeclaratorList|@TypedefDeclarators)?",\n',
        "new": '    "@DeclaratorList?",  # 变异：去掉 typedef 名后的声明符交替\n',
        "test": "tests/languages/c/test_c_declaration_spec_order.py",
    },
    {
        "why": "指针限定符（C99 §6.7.6 `* type-qualifier-list_opt`）：去掉 `@TypeQualifier*`"
               " ⇒ `int * const q;` / `const S * const p` 不可解析（cJSON 55 处命中；"
               "循环 #44 补）",
        "file": "grammar/c/01_declarations.toml",
        "old": '    "symbol.base.multiple",\n    "@TypeQualifier*",\n    "@Pointer?",\n',
        "new": '    "symbol.base.multiple",\n    "@Pointer?",  # 变异：去掉指针限定符\n',
        "test": "tests/languages/c/test_c_declaration_spec_order.py",
    },
    {
        "why": "无名抽象指针形参（C99 §6.7.6 `void f(void *, size_t);`）靠 ParamDecl 的"
               "`@Pointer`/`@TypedefAbstractDeclarator` 两支：去掉后真实头文件高频原型"
               "整条不可解析（zlib 原型声明命中；循环 #45 补）",
        "file": "grammar/c/01_declarations.toml",
        "old": '    "(@Declarator|@TypedefDeclarator|@Pointer|@TypedefAbstractDeclarator)?",\n',
        "new": '    "(@Declarator|@TypedefDeclarator)?",  # 变异：去掉无名抽象声明符\n',
        "test": "tests/languages/c/test_c_abstract_declarators.py",
    },
    {
        "why": "G4 typedef 名强转靠解析期符号注册（`[Rule.parser] register`）给 "
               "`_ScopeStack` 填 typedef 名：去掉 register 调用 ⇒ 所有 `(T)x` "
               "强转不可解析/退回启发式（真实 C 语料 cJSON/zlib 命中；循环 #49 补）",
        "file": "parser/parser_core.py",
        "old": "                    if name:\n                        self.scope_stack.register(name, kind)",
        "new": "                    if name:\n                        pass  # 变异：去掉符号注册",
        "test": "tests/languages/c/test_c_typedef_cast_symbols.py",
    },
    {
        "why": "规则级符号门控（`[Rule.parser] requires_symbol`）是 `(a)*b` 仍按"
               "乘法的唯一保证：门控失效 ⇒ 任何括号内标识符都被当类型名，变量"
               "乘法被误读成强转（解析期符号判定语义错误；循环 #49 补）",
        "file": "parser/parser_core.py",
        "old": "        kinds = set(self.symbol_namespaces.get(namespace) or ())\n        if not kinds:\n            return True",
        "new": "        return True  # 变异：门控失效（不查命名空间）",
        "test": "tests/languages/c/test_c_typedef_cast_symbols.py",
    },
    {
        "why": "预处理器宏展开时序（T1）：展开器按定义/取消事件逐行重建可见宏集。"
               "关闭时间线 ⇒ 定义前文本被最终表误展开（zlib gzgetc 型真实语料截断）",
        "file": "preprocessor/_expand.py",
        "old": "    timeline = events is not None",
        "new": "    timeline = False  # 变异：关闭定义时间线",
        "test": "tests/engine/preprocessor/test_expand_timeline.py",
    },
    {
        "why": "include 内容在包含点用当时可见宏集预展开（T1/A2）：关掉后头内"
               "原型被头内后置宏二次展开（gzgetc 型），或头内文本被宿主最终表二次展开",
        "file": "preprocessor/primitives/include.py",
        "old": '        if ctx.get("_preexpand_includes", True) and inc_clean:',
        "new": "        if False and inc_clean:  # 变异：关闭 include 内预展开",
        "test": "tests/engine/preprocessor/test_expand_timeline.py",
    },
    {
        "why": "include 子扫描继承包含点宏环境（T1 连带修复）：include guard 必须跨多次"
               "include 可见，否则同一守卫头重复铺入、类型二次定义（真实 zlib TAG001 命中）",
        "file": "preprocessor/primitives/include.py",
        "old": '            predefined=dict(ctx.get("_active_defs") or {}),',
        "new": "            predefined=None,  # 变异：不继承包含点宏环境",
        "test": "tests/engine/preprocessor/test_expand_timeline.py",
    },
    {
        "why": "linter 表达式注释回退（#52）：宏体尾注释进三元 ?: 中间时 pratt 停住/"
               "抛错，须用滤注释视图重试；关闭回退 ⇒ crc32 形态误报（真实 C 语料门禁红）",
        "file": "linter/checkers/expression.py",
        "old": "        view, pos_map = view_info",
        "new": "        return None  # 变异：关闭注释回退\n        view, pos_map = view_info",
        "test": "tests/engine/linter/test_linter_expression_comments.py",
    },
    {
        "why": "typedef 名复合字面量（T2a）：CompoundLiteral 类型名收 @CastTypedefName 门控支；"
               "去掉后 `(t){1}` 只能走已退役的 raw 兜底（无 pre_scan 时整句误报）",
        "file": "grammar/c/00_expressions.toml",
        "old": '    "@CastTypeName|@CastTypedefName",\n    "bracket.r_parentheses",\n    "@InitList",',
        "new": '    "@CastTypeName",  # 变异：去掉 typedef 名复合字面量\n    "bracket.r_parentheses",\n    "@InitList",',
        "test": "tests/languages/c/test_c_compound_literal.py",
    },
    {
        "why": "T3-⑤ L1 声明化：mapping entry 的 `source.resolved_attr` 是成品扁平行唯一来源；"
               "删除该声明键 ⇒ 成品行不再注入，typed_ports 行来源/嵌套/invert 判据必红",
        "file": "grammar/verilog/plugins/typed_ports/_mapping.py",
        "old": "        \"resolved_attr\": \"resolved_ports\",\n",
        "new": "",
        "test": "tests/languages/verilog/test_typed_ports.py",
    },

    # ── 符号表快照/回滚（task-22 三条自证 + parse 重建；原 _drafts/task22_revert.py）──
    {
        "why": "快照不含符号 store（回到第 7 位恒 None 的旧语义）⇒ pratt 内提前注册的"
               "符号不随回滚撤销，规则退出后残留在符号表（跨规则串味）",
        "file": "parser/parser_core.py",
        "old": "            self._symbol_store.snapshot() if self._symbol_store is not None else None,\n",
        "new": "            None,  # 变异：快照不含符号 store\n",
        "test": "tests/engine/parser/test_symbol_rollback.py",
    },
    {
        "why": "restore 只截栈、不撤销同深度 register ⇒ 同深度重注册的符号回滚后仍生效"
               "（`_register_log` 存在但没用上）",
        "file": "parser/parser_core.py",
        "old": "        for scope_idx, name, prev in reversed(self._register_log[log_len:]):\n",
        "new": "        for scope_idx, name, prev in []:  # 变异：不撤销同深度 register\n",
        "test": "tests/engine/parser/test_symbol_rollback.py",
    },
    {
        "why": "pratt 规则不再推作用域帧 ⇒ 寄存器名在表达式解析期间泄漏到外层作用域，"
               "退出（含失败）后不清理",
        "file": "parser/_production.py",
        "old": "    if getattr(rule, \"pratt\", False):\n        scope_pushed = _push_rule_scope(self, rule)\n",
        "new": "    if getattr(rule, \"pratt\", False):\n        scope_pushed = False  # 变异：不推作用域帧\n",
        "test": "tests/engine/parser/test_symbol_rollback.py",
    },
    {
        "why": "parse() 不重建/不绑定符号 store ⇒ 跨 parse 复用时上一轮 root 作用域注册"
               "残留，本轮 `lookup` 读到过期符号",
        "file": "parser/parser_core.py",
        "old": "        self.scope_stack = _ScopeStack()\n        context = ParseContext(tokens)\n        context.bind_symbol_store(self.scope_stack)\n",
        "new": "        context = ParseContext(tokens)  # 变异：不重建、不绑定符号 store\n",
        "test": "tests/engine/parser/test_symbol_rollback.py",
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
