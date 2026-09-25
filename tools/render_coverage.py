"""render_coverage.py — 语言包渲染覆盖率盘点（原文打印的前置度量）。

**为什么需要它**（2026-09-25 实测）：引擎对"没有 `[Rule.renderer.layout]` 的规则"
**静默输出空串**（不报错）——`grammar/c` 实测 `int x;` 渲染结果是 `''`。
即"缺布局"是一种**无声的保真度损失**，靠人肉逐条试才发现不了。故先量化：
哪些规则有渲染配置、哪些没有、哪些缺字段绑定（`{ ref = … }` 依赖 node 绑定）。

用法::

    python tools/render_coverage.py                # 默认 grammar/verilog
    python tools/render_coverage.py grammar/c
    python tools/render_coverage.py grammar/c --missing   # 只列缺布局的规则

判据（与 verilog 对照）：verilog 是成熟参考，其覆盖率即"该有的样子"；
新语言包（如 c）先从**叶子规则**补齐（叶子没有子节点依赖，补起来最省）。

Doc: docs/gaps/gap-language-pack-scope.md（C 包渲染面现状）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config_registry import ConfigRegistry  # noqa: E402
from core.define import GrammarRulesRegister  # noqa: E402
from parser import setup_grammar  # noqa: E402


def _has_render(rule) -> bool:
    """规则是否带渲染配置（layout 或 body——两者都是引擎认的渲染声明）。"""
    cfg = getattr(rule, "renderer", None)
    if not isinstance(cfg, dict):
        return False
    return bool(cfg.get("layout") or cfg.get("body") or cfg.get("ref"))


def _node_fields(rule) -> set[str]:
    """规则 node 绑定里的字段名（`{ ref = … }` 能引用的东西）。"""
    from core.define import GrammarRule  # noqa: F401  仅说明类型

    parser_cfg = getattr(rule, "parser", None) or {}
    node = parser_cfg.get("node") if isinstance(parser_cfg, dict) else None
    return set(node) if isinstance(node, dict) else set()


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染覆盖率盘点")
    ap.add_argument("pack", nargs="?", default="grammar/verilog")
    ap.add_argument("--missing", action="store_true", help="只列缺渲染配置的规则")
    args = ap.parse_args()

    plugins = str(Path(args.pack) / "plugins")
    ConfigRegistry.load_language(args.pack, plugins_dir=plugins)
    try:
        rules = setup_grammar(args.pack, GrammarRulesRegister())
    finally:
        ConfigRegistry.load_language(
            "grammar/verilog", plugins_dir="grammar/verilog/plugins"
        )

    covered, missing = [], []
    for name in sorted(rules):
        (covered if _has_render(rules[name]) else missing).append(name)

    total = len(rules)
    print(f"[render-coverage] {args.pack}：规则 {total} 条")
    print(f"  有渲染配置 {len(covered)}（{len(covered) / total:.0%}）")
    print(f"  缺渲染配置 {len(missing)}")

    if args.missing:
        print("\n缺渲染配置的规则（建议从**叶子**补起——没有子节点依赖）：")
        for name in missing:
            fields = sorted(_node_fields(rules[name]))
            leaf = "叶子" if not fields else "有字段"
            print(f"  {name:<22} [{leaf}] node 字段: {', '.join(fields) or '（无）'}")
    else:
        print("\n缺渲染配置（前 20）：")
        for name in missing[:20]:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
