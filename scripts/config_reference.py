#!/usr/bin/env python3
"""
配置参考生成器 — 完整参数评估 + 使用指导。

用法:
    python scripts/config_reference.py          # 输出到终端
    python scripts/config_reference.py --doc    # 输出 Markdown 到 docs/
"""

import os, sys, tomllib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "token.toml": "grammar/token.toml",
    "symbol_level.toml": "grammar/symbol_level.toml",
    "normalize_config.toml": "transform/config/normalize_config.toml",
}

LANG_FILES = {
    "_token.toml": "词法定义（符号、关键字、字面量、括号等）",
    "_symbol_level.toml": "运算符优先级（[[operator]] 列表）",
    "00_blocks.toml": "块结构规则（缩进、begin/end 等）",
    "01_module.toml": "模块/类/函数等顶层容器规则",
    "02_declarations.toml": "变量/端口/参数等声明规则",
    "03_always.toml": "过程块规则（always、initial 等）",
    "04_statements.toml": "语句规则（if、case、赋值等）",
    "05_expressions.toml": "表达式与字面量规则",
}

# (领域, 参数, 价值, 复杂度, 一句话说明, 使用建议)
PARAM_EVALS = [
    (
        "Parser",
        "production",
        "🔴 必要",
        "★★☆",
        "语法产生式，定义如何匹配 token 序列",
        "每个规则都必须有。写错这里解析器就搞不懂语法。",
    ),
    (
        "Parser",
        "[RuleName.node]",
        "🔴 必要",
        "★★☆",
        "将匹配结果映射到 AST 节点的属性",
        "每个 production 的匹配项用 $1/$2/... 引用，支持 . 路径如 $4.items。",
    ),
    (
        "Parser",
        "end_case",
        "🟡 常用",
        "★☆☆",
        "标识该规则是'语句级'规则",
        "有 end_case 的规则会被列入语句候选列表。只有作为独立语句的规则需要加（如 if, always, assign）。表达式规则不需要。",
    ),
    (
        "Parser",
        "inline",
        "🟡 常用",
        "★★☆",
        "内联标记：将本规则在 AST 中压平消除",
        "用于包装器规则（如 Statement, PortDecl）。inline=true 时该节点在规范化阶段被消除，子节点直接上提。",
    ),
    (
        "Parser",
        "pratt",
        "🟢 可选",
        "★★★",
        "启用 Pratt 解析器处理该规则",
        "用于表达式规则。Pratt 解析器处理运算符优先级。Expression 通常需要。",
    ),
    (
        "Parser",
        "block_start/end",
        "🟢 可选",
        "★★☆",
        "块的开始/结束 token 类型",
        "用于 Root 和 Block 规则。Root 用空字符串，Block 用缩进标记。普通规则一般不需要。",
    ),
    (
        "Renderer",
        "layout/head",
        "🔴 必要",
        "★★☆",
        "节点头部/内联布局表达式",
        "决定渲染时头部如何输出。可以用字符串（纯文本）或复杂表达式（line/ref/join 等）。",
    ),
    (
        "Renderer",
        "body",
        "🟡 常用",
        "★★☆",
        "主体内容配置",
        "指定从哪里获取子节点（source = 'body'）以及缩进（indent = true）。",
    ),
    (
        "Renderer",
        "tail",
        "🟡 常用",
        "★☆☆",
        "尾部字面量",
        "如 endmodule、endfunction、end 等。渲染器自动在 tail 前加换行。",
    ),
    (
        "Renderer",
        "tail_break",
        "🟡 常用",
        "★☆☆",
        "tail 前后间距控制",
        "1 = tail 独占一行；2 = tail 独占一行 + 尾部空行。数值越大空行越多。",
    ),
    (
        "Renderer",
        "body_role",
        "🟢 可选",
        "★★☆",
        "主体角色标记",
        "flatten = 展开子节点到父级；direct = body 替换父节点。偶尔需要。",
    ),
    (
        "Renderer",
        "override",
        "🟢 可选",
        "★★★",
        "子规则布局属性覆盖",
        "如 [ParentRule.override] ChildRule = { tail_break = 2 }。同一子规则在不同父规则下需要不同间距时使用。",
    ),
    (
        "Renderer",
        "布局 DSL 原语",
        "🟡 常用",
        "★★★",
        "布局表达式内部元素",
        "ref=引用子节点；soft=软换行；break=硬换行；join=分隔列表；group=组；line=行；opt=可选；indent=缩进。",
    ),
    (
        "SemAnalyzer",
        "scope",
        "🟡 常用",
        "★★☆",
        "声明本规则创建新作用域",
        "scope = { name_attr = 'xxx', kind = 'xxx' }。模块/函数/for 块等需要。",
    ),
    (
        "SemAnalyzer",
        "symbol",
        "🟡 常用",
        "★★☆",
        "声明本规则注册符号到当前作用域",
        "symbol = { kind = 'xxx', name_attr = 'xxx' }。变量/端口/参数声明需要。",
    ),
    (
        "SemAnalyzer",
        "identifier_ref",
        "🟢 可选",
        "★☆☆",
        "声明本规则的产出节点是标识符引用",
        "加在 Identifier 规则上，值 = true。触发作用域链查找。",
    ),
    (
        "Lexer",
        "space / newline",
        "🔴 必要",
        "★☆☆",
        "空白和换行符定义",
        "几乎所有语言都需要。空白符 ' ' / '\\t'，换行符 '\\n'。",
    ),
    (
        "Lexer",
        "comment",
        "🟡 常用",
        "★☆☆",
        "注释边界符",
        "定义注释起始字符。Verilog/C 用 '/'，Python 用 '#'，VHDL 用 '--'。",
    ),
    (
        "Lexer",
        "symbol.base",
        "🔴 必要",
        "★★☆",
        "单字符运算符",
        "定义所有单字符运算符：+ - * / % = , ; : . ( ) [ ] { } @ # $ ~ ^ & | ! < > 等。",
    ),
    (
        "Lexer",
        "symbol.extend",
        "🟡 常用",
        "★★☆",
        "多字符运算符",
        "定义所有多字符运算符：== != >= <= << >> && || ++ -- += -= -> ** :: 等。",
    ),
    (
        "Lexer",
        "bracket",
        "🔴 必要",
        "★☆☆",
        "括号对定义",
        "所有括号对：( ) [ ] { } < > 等。Lexer 需要它们做括号匹配。",
    ),
    (
        "Lexer",
        "literal",
        "🟡 常用",
        "★★☆",
        "字面量正则",
        "定义字符串和数字字面量的正则表达式。",
    ),
    (
        "Lexer",
        "id.keyword",
        "🔴 必要",
        "★★☆",
        "关键字列表",
        "每个关键字一行。词法分析时优先匹配。关键字是语言最核心的词汇表。",
    ),
    (
        "Lexer",
        "id.id",
        "🔴 必要",
        "★☆☆",
        "标识符正则",
        "定义合法标识符的正则。大多数语言是 [a-zA-Z_][a-zA-Z0-9]*。",
    ),
    (
        "Pratt",
        "[[operator]]",
        "🟡 常用",
        "★★★",
        "运算符优先级定义",
        "symbol=字面值; arity=目数; assoc=left/right; position=prefix/postfix; second=三目第二个符号。优先级数组下标决定。",
    ),
    (
        "Normalizer",
        "[extract_value]",
        "🟢 可选",
        "★★☆",
        "自动提取字符串值的节点前缀/名",
        "根据前缀 keyword./symbol. 自动提取为纯字符串。",
    ),
    (
        "Normalizer",
        "[eliminate]",
        "🟡 常用",
        "★★☆",
        "消除的包装节点类型",
        "optional/repeat/sequence 在规范化阶段消除。一般不动。",
    ),
    (
        "Normalizer",
        "[merge]/[flatten]/[fields]",
        "🟢 可选",
        "★★☆",
        "AST 规范化辅助配置",
        "merge=合并属性; flatten=展开容器; fields=字段名。一般用缺省值。",
    ),
]


def load_toml(rel_path):
    ap = os.path.join(PROJECT_ROOT, rel_path)
    if not os.path.isfile(ap):
        return {}
    with open(ap, "rb") as f:
        return tomllib.load(f)


def render_markdown():
    L = []
    w = L.append

    w("# GrammarFlow 配置参考")
    w("")
    w("本文档由 `scripts/config_reference.py` 自动生成。")
    w("")

    # ── 参数评估总表 ──
    w("## 参数评估总表")
    w("")
    w("| 领域 | 参数 | 价值 | 复杂度 | 说明 | 使用建议 |")
    w("|------|------|------|--------|------|---------|")
    for area, name, value, complexity, desc, guide in PARAM_EVALS:
        w(f"| {area} | `{name}` | {value} | {complexity} | {desc} | {guide} |")
    w("")

    # ── 目录结构 ──
    w("## 目录结构")
    w("")
    w("| 文件 | 用途 | 缺省继承 |")
    w("|------|------|---------|")
    for fn, desc in LANG_FILES.items():
        fb = (
            "✓ 有全局缺省"
            if fn in ("_token.toml", "_symbol_level.toml")
            else "— 必须编写"
        )
        w(f"| `{fn}` | {desc} | {fb} |")
    w("")

    # ── 词法 ──
    w("## 词法定义 (`_token.toml`)")
    w("")
    w("合并加载：全局 `grammar/token.toml` + 语言 `_token.toml` 覆盖。")
    w("")
    w("| 章节 | 用途 | 全局缺省 |")
    w("|------|------|---------|")
    td = load_toml(DEFAULTS["token.toml"])
    for s in [
        "space",
        "newline",
        "comment",
        "symbol.base",
        "symbol.extend",
        "bracket",
        "literal",
        "id.id",
        "id.keyword",
    ]:
        in_def = "✓" if s in td else "—"
        descs = {
            "space": "空白",
            "newline": "换行",
            "comment": "注释",
            "symbol.base": "单字符运算符",
            "symbol.extend": "多字符运算符",
            "bracket": "括号",
            "literal": "字面量",
            "id.id": "标识符",
            "id.keyword": "关键字",
        }
        w(f"| `[{s}]` | {descs.get(s,s)} | {in_def} |")
    w("")

    # ── 运算符优先级 ──
    w("## 运算符优先级 (`_symbol_level.toml`)")
    w("")
    w("| 字段 | 必填 | 说明 |")
    w("|------|------|------|")
    w("| `symbol` | ✓ | 运算符字面值 |")
    w("| `arity` | ✓ | 目数：1/2/3 |")
    w("| `assoc` | | 结合性：`left` / `right` |")
    w("| `position` | 一元 | `prefix` / `postfix` |")
    w("| `second` | 三目 | 第二个符号（如 `?` 的 `:`） |")
    w("")
    sd = load_toml(DEFAULTS["symbol_level.toml"])
    ops = sd.get("operator", [])
    if ops:
        w("| 优先级 | 符号 | 目数 | 结合性 |")
        w("|--------|------|------|--------|")
        for i, o in enumerate(ops, 1):
            w(f"| {i} | `{o['symbol']}` | {o['arity']} | {o.get('assoc','left')} |")
        w("")

    # ── 语法规则参数详解 ──
    w("## 语法规则参数详解")
    w("")

    w("### `production`（🔴 必要）")
    w("")
    w("语法产生式，支持：")
    w('- `"keyword.xxx"` — 精确匹配 token 类型')
    w("- `@RuleName` — 引用另一规则")
    w("- `@A|@B` — 分支")
    w("- `(...)?` — 可选，`(...)*` — 零或多次，`(...)+` — 一或多次")
    w("")

    w("### `[RuleName.node]`（🔴 必要）")
    w("")
    w("属性映射。`$1` = 第一个匹配项，`$2.value` = 第二个匹配项的 value 属性。")
    w("")

    w("### `end_case`（🟡 常用）")
    w("")
    w("语句结束符列表。有此属性的规则被视为语句级规则，可被 `parse_sentence()` 识别。")
    w("")

    w("### `inline` / `pratt`（🟡 常用 / 🟢 可选）")
    w("")
    w("- `inline=true` — 包装器规则，AST 中消除")
    w("- `pratt=true` — 用 Pratt 解析器处理运算符优先级")
    w("")

    w("### `scope` / `symbol` / `identifier_ref`（语义自声明）")
    w("")
    w("```toml")
    w('scope = { name_attr = "xxx", kind = "xxx" }           # 建作用域')
    w('symbol = { kind = "xxx", name_attr = "xxx" }         # 注册符号')
    w("identifier_ref = true                                     # 标识符引用")
    w("```")
    w("")

    w("### `tail_break`（🟡 常用）")
    w("")
    w("- `1` — 独占一行")
    w("- `2` — 独占一行 + 尾部空行")
    w("")

    w("### `override`（🟢 可选）")
    w("")
    w("```toml")
    w("[ParentRule.override]")
    w("ChildRule = { tail_break = 2 }")
    w("```")
    w("")

    # ── 检查清单 ──
    w("## 快速检查清单")
    w("")
    w("### 词法 (`_token.toml`)")
    w("- ☐ space / newline 定义了空白和换行")
    w("- ☐ comment 定义了注释（如果有）")
    w("- ☐ symbol.base 覆盖了所有单字符运算符")
    w("- ☐ symbol.extend 覆盖了所有多字符运算符")
    w("- ☐ bracket 定义了所有括号对")
    w("- ☐ id.keyword 列出了所有关键字")
    w("- ☐ id.id 定义了标识符正则")
    w("- ☐ literal 定义了字符串和数字字面量")
    w("")
    w("### 语法规则 (00-05)")
    w("- ☐ 每个规则都有 `production`")
    w("- ☐ 每个 production 都有 `[RuleName.node]` 映射")
    w("- ☐ 语句级规则有 `end_case`")
    w("- ☐ 包装器规则有 `inline = true`")
    w("- ☐ 创建作用域的规则有 `scope = { ... }`")
    w("- ☐ 注册符号的规则有 `symbol = { ... }`")
    w("- ☐ 标识符节点有 `identifier_ref = true`")
    w("- ☐ 布局表达式覆盖了 layout/head + body + tail")
    w("")
    w("### 运算符优先级")
    w("- ☐ 所有二元运算符按优先级从低到高排列")
    w("- ☐ 一元运算符加了 `position`")
    w("- ☐ 三目运算符加了 `second`")
    w("")

    # ── 快速起步 ──
    w("## 快速起步：添加新语言")
    w("")
    w("```")
    w("1. cp -r grammar/rules_verilog grammar/rules_mylang")
    w("2. 修改 _token.toml → 替换关键字、增删运算符")
    w("3. 修改 00-05 规则 → 改写 production/node、加 scope/symbol")
    w("4. 修改 _symbol_level.toml → 调整运算符优先级")
    w("5. 改 RULES_DIR 指向新目录，运行")
    w("```")
    w("")

    return "\n".join(L)


def main():
    md = render_markdown()
    if "--doc" in sys.argv:
        doc_dir = os.path.join(PROJECT_ROOT, "docs")
        os.makedirs(doc_dir, exist_ok=True)
        path = os.path.join(doc_dir, "config_reference.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ 已生成: {path}")
    else:
        print(md)


if __name__ == "__main__":
    main()
