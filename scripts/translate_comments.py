"""Batch convert Chinese docstrings/comments to English.

Run: python scripts/translate_comments.py
"""
import re, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRANSLATIONS = {
    # === analyzer/primitives/registry.py ===
    "analyzer/primitives/registry.py": [
        (r'"""registry\.py — 分析器原语注册中心.*?"""',
         '"""registry.py — analyzer primitive registry.\n\n'
         'Symmetric design to transform/post/engine/registry.py but separate concerns.\n'
         'Analyzer primitives handle semantic analysis during AST traversal\n'
         '(scope, symbols, reference resolution).\n'
         'Transform primitives handle post-phase AST modification\n'
         '(expansion, replacement, deletion).\n'
         '\n'
         'Registered primitives are injected into SemanticAnalyzer._walk_node pipeline,\n'
         'executed in the order declared in TOML [RuleName.analyzer] configuration.\n'
         '"""'),
        (r'# ── 原语签名 ──',
         '# ── Primitive signature ──'),
        (r'# AnalyzerPrimitive = Callable\[\n#     analyzer: SemanticAnalyzer,\s+# 分析器实例（持有 scope/errors 状态）\n#     node: Node,\s+# 当前 AST 节点\n#     config: dict,\s+# 该规则 analyzer 配置字典\n# \] -> None\n#\n# 原语通过副作用修改 analyzer 的内部状态（scope、symbols、errors 等）。',
         '# AnalyzerPrimitive = Callable[\n#     analyzer: SemanticAnalyzer,    # Analyzer instance (holds scope/errors)\n#     node: Node,                    # Current AST node\n#     config: dict,                  # Analyzer config dictionary for this rule\n# ] -> None\n#\n# Primitives modify the analyzer\'s internal state via side effects (scope, symbols, errors).'),
        (r'# ── 原语注册表 ──', '# ── Primitive registry ──'),
        (r'"""注册一个分析器原语\n\n    Args:\n        name: 原语名称，TOML 配置中通过此名称引用\n        fn: 原语函数，签名见 AnalyzerPrimitive\n    """',
         '"""Register an analyzer primitive.\n\n    Args:\n        name: Primitive name, referenced in TOML configuration.\n        fn: Primitive function, signature per AnalyzerPrimitive.\n    """'),
        (r'"""按名称获取已注册的原语"""',
         '"""Get a registered primitive by name."""'),
        (r'"""检查原语是否已注册"""',
         '"""Check if a primitive is registered."""'),
    ],

    # === normalizer/__init__.py ===
    "normalizer/__init__.py": [
        (r'"""normalizer/ — AST 规范化模块\n\n消除 Parser 产生的 temporary/structural 节点.*?"""',
         '"""normalizer/ — AST normalization module\n\n'
         'Eliminates temporary/structural nodes produced by the Parser\n'
         '(optional, repeat, seq wrappers), producing a clean AST\n'
         'ready for semantic analysis and rendering.\n'
         '"""'),
        (r'# 核心消除集合（只消除 parser 内部结构）',
         '# Core elimination set (parser-internal structures only)'),
        (r'# optional  → 空值过滤', '# optional  → filter None'),
        (r'# repeat    → 零次或多次重复（展开为列表）', '# repeat    → zero-or-more (unfold to list)'),
        (r'# seq       → 序列（展开为列表）', '# seq       → sequence (unfold to list)'),
        (r'# 注意：语法层结构（如 DeclaratorList）不在这里，保留原样',
         '# Note: grammar-level structures (e.g. DeclaratorList) are preserved as-is'),
        (r'"""消除 optional / repeat / seq 包装节点，生成规范 AST。\n\n    Args:\n        node: 原始 AST（可能包含 optional/repeat/seq 节点）\n        layouts: 布局配置字典（用于识别范围节点）\n    Returns:\n        规范化后的 AST（不含 optional/repeat/seq 节点）\n    """',
         '"""Eliminate optional/repeat/seq wrapper nodes, producing a normalized AST.\n\n    Args:\n        node: Raw AST (may contain optional/repeat/seq nodes).\n        layouts: Layout config dict (for identifying range nodes).\n    Returns:\n        Normalized AST (without optional/repeat/seq nodes).\n    """'),
        (r'# 已规范化，直接返回', '# Already normalized, return as-is'),
        (r'# 可能是普通 Node，也可能是序列包装', '# Could be plain Node or sequence wrapper'),
        (r'"""规范化一个子节点（处理 repeat 展开）"""',
         '"""Normalize a child node (handles repeat unfolding)."""'),
        (r'"""规范化 repeat 节点（展开为列表）"""',
         '"""Normalize a repeat node (unfold to list)."""'),
        (r'# 保留 None 哨兵（后面 parser 可能还要用）',
         '# Keep None sentinel (parser may need it later)'),
    ],

    # === renderer/renderer.py ===
    "renderer/renderer.py": [
        (r'"""\nRenderer — AST \+ 布局规则驱动的代码生成器\n\n只包含 DSL 原语.*?"""',
         '"""Renderer — AST + layout-rule-driven code generator.\n\n'
         'Contains only DSL primitives (text/ref/join/group/line/indent/opt).\n'
         'All language-specific knowledge comes from TOML layout rules.\n'
         'The AST normalizer converts parser-internal constructs\n'
         '(keyword/symbol/optional/repeat/sequence/first+rest)\n'
         'before rendering.\n'
         '"""'),
        (r'# 从 layout 配置中提取布局求值',
         '# Extract layout evaluation from layout config'),
        (r'# 按 key 分派到 primitives',
         '# Dispatch to primitives by key'),
        (r'# 缓存所有 layout 配置',
         '# Cache all layout configs'),
        (r'# 递归渲染\n        # 子节点的 layout 优先于父节点的 body',
         '# Recursive rendering\n        # Child node layout takes precedence over parent body'),
        (r'# 直接返回 body 的 flat doc',
         '# Return flat doc from body'),
        (r'"""递归渲染 body 子节点"""',
         '"""Recursively render body children."""'),
    ],

    # === analyzer/__init__.py inline ===
    "analyzer/__init__.py": [
        (r'# 5 模块',
         '# 5 modules'),
        (r'# 职责',
         '# Responsibilities'),
        (r'# 设计原则',
         '# Design principles'),
        (r'# 语言无关',
         '# Language-agnostic'),
        (r'# 可扩展',
         '# Extensible'),
    ],
}


def translate_file(filepath: str, patterns: list) -> bool:
    """Apply regex replacements to a file."""
    fullpath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filepath)
    if not os.path.exists(fullpath):
        print(f"  SKIP: {filepath} not found")
        return False
    with open(fullpath, 'r', encoding='utf-8') as f:
        content = f.read()
    changed = False
    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        if new_content != content:
            changed = True
            content = new_content
    if changed:
        with open(fullpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  updated {filepath}")
    else:
        print(f"  no change {filepath}")
    return changed


if __name__ == '__main__':
    for filepath, patterns in TRANSLATIONS.items():
        translate_file(filepath, patterns)
    print("done")
