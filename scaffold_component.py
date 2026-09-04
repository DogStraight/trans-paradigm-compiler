"""scaffold_component.py — 新组件脚手架。

生成 plugins/<name>/ 骨架（tpc.toml + 00_xxx.toml + _handler.py），
挂到语言包 tpc.toml 的 [plugins] enabled。

用法: python main.py new component <name> [--lang verilog]
"""

import os

_TEMPLATES = {
    "tpc.toml": """# <NAME> 组件 — 元数据
[lexer]
token_ext = { file = "_token_ext.toml", required = false }

[grammar]
files = ["00_<name>.toml"]

[analyzer]
primitives = []
handlers = []

[transform]
slots = []
handlers = []
""",
    "00_<name>.toml": """# <NAME> 语法规则（组件）
# 通过 inject 挂到基础语法（见 core/component_protocol.md）

[<RuleName>.inject]
targets = ["@ModuleItem"]

[<RuleName>]
is_statement = true

[<RuleName>.parser]
production = ["@Identifier", "symbol.base.semicolon"]

[<RuleName>.parser.node]
name = "$1"

[<RuleName>.renderer]
layout = { line = [{ ref = "name" }, ";"] }
""",
    "_handler.py": '''"""<NAME> 组件处理器。

三种注册方式（见 core/component_protocol.md）：
  - transform 槽位：@register_transform_slot("name")
  - analyzer 原语：register_primitive("name", fn)
  - transform 插件：@register_plugin 类（TransformPlugin 子类）
"""

# 示例：transform 槽位
# from core.plugin_loader import register_transform_slot
#
# @register_transform_slot("my_slot")
# def my_slot(node, ctx):
#     """节点级变换：返回新节点/None/原节点。"""
#     return node
''',
}


def scaffold_component(name: str, lang: str = "verilog") -> None:
    """生成 plugins/<name>/ 组件骨架。"""
    root = os.path.dirname(os.path.abspath(__file__))
    plugins_dir = os.path.join(root, "grammar", lang, "plugins", name)
    if os.path.isdir(plugins_dir):
        print(f"[scaffold] 已存在: {plugins_dir}")
        return
    os.makedirs(plugins_dir)

    for fname, content in _TEMPLATES.items():
        path = os.path.join(plugins_dir, fname.replace("<name>", name))
        filled = content.replace("<NAME>", name.title()).replace("<name>", name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(filled)

    # 挂载到语言包 tpc.toml
    lang_tpc = os.path.join(root, "grammar", lang, "tpc.toml")
    if os.path.isfile(lang_tpc):
        with open(lang_tpc, encoding="utf-8") as f:
            src = f.read()
        if name not in src:
            import re
            m = re.search(r'enabled = \[(.*?)\]', src, re.S)
            if m:
                new_list = m.group(1).rstrip().rstrip("]").rstrip() + f', "{name}"'
                src = src[: m.start(1)] + new_list + "]" + src[m.end(1):]
                with open(lang_tpc, "w", encoding="utf-8", newline="") as f:
                    f.write(src)
                print(f"[scaffold] 已挂载到 grammar/{lang}/tpc.toml [plugins] enabled")

    print(f"[scaffold] 组件已创建: {plugins_dir}")
    print(f"          编辑 tpc.toml 声明语法/处理器，写规则与 handler 后跑测试")
