"""Batch convert Chinese docstrings/comments to English — phase 2."""
import re, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rep(filepath: str, replacements: list) -> None:
    """Apply string replacements to a file."""
    path = os.path.join(ROOT, filepath)
    if not os.path.exists(path):
        print(f"  SKIP: {filepath} not found")
        return
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    changed = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed = True
        else:
            print(f"  MISS: {filepath} / {old[:40]!r}")
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  updated {filepath}")
    else:
        print(f"  no change {filepath}")


def rex(filepath: str, replacements: list) -> None:
    """Apply regex replacements to a file."""
    path = os.path.join(ROOT, filepath)
    if not os.path.exists(path):
        print(f"  SKIP: {filepath} not found")
        return
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    changed = False
    for pattern, repl in replacements:
        new = re.sub(pattern, repl, content, flags=re.DOTALL)
        if new != content:
            changed = True
            content = new
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  updated {filepath}")
    else:
        print(f"  no change {filepath}")


# === renderer/renderer.py ===
rep('renderer/renderer.py', [
    ('"""代码生成器（Renderer）—— AST + 布局配置驱动',
     '"""Renderer — AST + layout config driven'),
    ('只包含 DSL 原语，引擎侧不包含任何语言特定知识。',
     'Contains only DSL primitives; engine has zero language-specific knowledge.'),
    ('"""从 layout 配置中提取布局求值"""',
     '"""Evaluate layout from layout config."""'),
])

# === linter/__init__.py ===
rex('linter/__init__.py', [
    (r'"""LSP 兼容的位置（0-based）。"""',
     '"""LSP-compatible position (0-based)."""'),
])

# === transform/config_driven.py inline comments ===
rep('transform/config_driven.py', [
    ('# 自动拉取 SemanticMappingPlugin 的映射表',
     '# Auto-pull mapping table from SemanticMappingPlugin'),
])

# === main.py ===
rep('main.py', [
    ('"""运行 Verilog 编译管线"""', '"""Run the Verilog compilation pipeline."""'),
    ('"""运行语法扫描器"""', '"""Run the syntax scanner."""'),
    ('print("  pipeline [test_name]  运行 Verilog 编译管线")',
     'print("  pipeline [test_name]  Run the Verilog compilation pipeline")'),
    ('print("  linter [input_file]   运行语法扫描器")',
     'print("  linter [input_file]   Run the syntax scanner")'),
])

# === verilog/run_pipeline.py ===
rep('verilog/run_pipeline.py', [
    ('# 模块级共享状态：rules/lexer/renderer/transformer 按 rules_dir 缓存，避免重复初始化',
     '# Module-level shared state: cache rules/lexer/renderer/transformer by rules_dir'),
    ('# Quiet-aware logger',
     '# Quiet-aware logger'),  # already English
])

# === verilog/run_all_tests.py ===
rep('verilog/run_all_tests.py', [
    ('# 日志抑制', '# Suppress logging'),
    ('# 判定测试结果', '# Determine test result'),
])

# === verilog/test_features.py ===
rep('verilog/test_features.py', [
    ('"""基础解析必须成功"""', '"""Basic parsing must succeed."""'),
])

# === transform/config_driven.py method docstrings ===
rex('transform/config_driven.py', [
    (r'    """遍历 AST 并执行所有匹配的变换"""',
     '    """Traverse AST and execute all matching transforms."""'),
    (r'    """遍历列表，扁平化处理变换结果\n\n        Args:\n            items: 子节点列表\n            parent: 父节点\n            parent_attr: 父节点中保存 items 的属性名\n        Returns:\n            处理后的节点列表\n        """',
     '    """Walk a list, flattening transform results.\n\n        Args:\n            items: Child node list.\n            parent: Parent node.\n            parent_attr: Attribute name on parent holding items.\n        Returns:\n            Processed node list.\n        """'),
    (r'    """将节点的属性展开为扁平 context dict\n\n        支持:\n            node\.foo              → context\["foo"\]\n            node\.sub\.name         → context\["sub\.name"\]\n            node\.sub_item         → context\["sub_item"\]  \(快捷方式\)\n\n        快捷方式：若一个 Node 有 name/content/value 主要值属性，\n        该属性的值会直接以 Node 名称为键注册（覆盖 Node 本身）。\n        """',
     '    """Flatten node attributes into a flat context dict.\n\n        Supports:\n            node.foo              → context["foo"]\n            node.sub.name         → context["sub.name"]\n            node.sub_item         → context["sub_item"]  (shortcut)\n\n        Shortcut: if a Node has a primary value attribute (name/content/value),\n        that value is registered directly under the node name (overriding the node itself).\n        """'),
])

# === grammar/rules_verilog_ext/_components/builtins/_semantic_mapping.py ===
rep('grammar/rules_verilog_ext/_components/builtins/_semantic_mapping.py', [
    ('"""SemanticMappingPlugin — 将分析器符号表转换为变换器映射表"""',
     '"""SemanticMappingPlugin — convert analyzer symbol table to transformer mapping table."""'),
    ('"""构建完整的语义映射表

    此表是变换器展开规则（type_decl, impl_binding 等）的输入，
    也是 transform_extra 输出文件的查找依据。
    """',
     '"""Build the complete semantic mapping table.\n\n    This table is the input for transformer expansion rules\n    (type_decl, impl_binding, etc.) and the lookup basis for\n    transform_extra output files.\n    """'),
])

# === grammar/rules_verilog_ext/_components/typed_ports/_bridge.py ===
rep('grammar/rules_verilog_ext/_components/typed_ports/_bridge.py', [
    ('"""将组件的 transform 槽位作为 TransformPlugin 运行。

    本插件遍历 AST，对每个节点检查是否有对应槽位名称的规则配置，
    若有则调用槽位处理函数。
    """',
     '"""Run component transform slots as a TransformPlugin.\n\n    Walks the AST and, for each node, checks if a corresponding slot\n    is configured; if so, invokes the slot handler.\n    """'),
    ('"""主入口：处理所有 typed_port 相关的变换"""',
     '"""Main entry: process all typed_port-related transforms."""'),
    ('"""扫描并构建类型映射表"""',
     '"""Scan and build the type mapping table."""'),
    ('"""处理所有 TypeDecl"""',
     '"""Process all TypeDecl nodes."""'),
    ('"""处理所有 ImplBinding"""',
     '"""Process all ImplBinding nodes."""'),
])

# === grammar/rules_verilog_ext/_components/typed_ports/_transform.py ===
rep('grammar/rules_verilog_ext/_components/typed_ports/_transform.py', [
    ('"""构建包装模块（删除原 TypeDecl）"""',
     '"""Build wrapper module (delete original TypeDecl)."""'),
    ('"""展开类型化端口（由 CDT 处理，此处透传）"""',
     '"""Expand typed ports (handled by CDT, pass-through here)."""'),
    ('"""自动连线（合并显式 + 自动展平的端口）"""',
     '"""Auto-connect ports (merge explicit + auto-flattened ports)."""'),
    ('"""替换 ImplBinding 为 ModuleInst"""',
     '"""Replace ImplBinding with ModuleInst."""'),
])

# === scripts/ast_debug.py ===
rep('scripts/ast_debug.py', [
    ('"""AST 调试工具"""', '"""AST debug utilities."""'),
    ('"""递归统计 AST 节点总数"""', '"""Recursively count total AST nodes."""'),
    ('"""统计各节点类型数量"""', '"""Count occurrences of each node type."""'),
])

print("done")
