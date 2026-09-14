"""preprocessor/macro_shape.py — 宏体形态分类（完整语法单元 vs 残缺片段）。

**包装解析**：宏体放进语言包声明的若干最小语法上下文（wrappers：stmt/decl/expr/
port），能完整解析 → 完整语法单元；全部失败 → 残缺片段。

用途：宏体入树的**投影粒度**选择前置——完整单元宏可走 token 级替换（独立成
AST 节点），残缺片段走文本级投影。本模块只**产出分类**；消费点由管线宏边界
处理（见 `preprocessor/README.md` + `pipeline/README.md`）。

包装模板与续接首 token 集是**语言语法知识**——由语言包 `[macro_shape]` 声明
（`grammar/<lang>/base/*.toml`），引擎只做通用包裹解析，语言知识不进代码。

Doc: preprocessor/README.md
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from core.config_registry import declare_cfg

_shape_cfg: dict = declare_cfg("preprocessor.macro_shape", {}, __name__, "_shape_cfg")

# 形态判定常量
KIND_STMT = "完整语句"
KIND_DECL = "完整声明"
KIND_EXPR = "完整表达式"
KIND_PARTIAL = "残缺片段"

# 探测顺序：外层包裹优先（语句 > 声明 > 表达式）——更"外层"的语法上下文先判定
_PROBE_ORDER: tuple[tuple[str, str], ...] = (
    ("stmt", KIND_STMT),
    ("decl", KIND_DECL),
    ("expr", KIND_EXPR),
)


def get_shape_config(cfg: dict | None = None) -> tuple[dict, list[str]]:
    """读取形态分类配置 → (wrappers 模板表, continue_leads 续接首 token 集)。"""
    cfg = _shape_cfg if cfg is None else cfg
    wrappers = cfg.get("wrappers") or {}
    leads = list(cfg.get("continue_leads") or [])
    return wrappers, leads


def _wrapper_tpl(spec: object) -> str:
    """取包裹模板（兼容旧字符串形态与 {tpl, pick, ...} 表形态）。"""
    if isinstance(spec, dict):
        return spec.get("tpl") or ""
    return spec if isinstance(spec, str) else ""


def classify_macro_body(
    body: str, probe: Callable[[str], bool], cfg: dict | None = None
) -> tuple[str, str]:
    """分类宏体形态，返回 `(判定, 依据)`；判定 ∈ KIND_* 四值。

    body  — 宏体源文本（`` `define NAME body `` 的 body 部分）
    probe — 片段解析探测：接收完整源码片段，能完整解析返回 True
    cfg   — 形态配置（缺省取语言包 `[macro_shape]`）
    """
    wrappers, leads = get_shape_config(cfg)
    stripped = body.lstrip()

    # 首 token 续接预过滤：以符号开头的宏体依赖前置上下文（残缺续段），
    # 包裹模板的宽松接受会误判（如 `+ 4` 被当一元正号、`= 1'b1` 被当端口默认值）。
    for lead in leads:
        if stripped.startswith(lead):
            head = stripped.split()[0][:12] if stripped.split() else stripped[:12]
            return KIND_PARTIAL, f"首 token 续接（{head}）"

    for key, kind in _PROBE_ORDER:
        tpl = _wrapper_tpl(wrappers.get(key))
        if not tpl:
            continue
        # 用 replace 而非 format：宏体可能含 `{`/`}`（如拼接 `{a,b}`），
        # str.format 会把花括号当占位符抛错。
        if probe(tpl.replace("{b}", body)):
            return kind, f"{key} 包裹解析成功"
    return KIND_PARTIAL, "全部包裹失败"


# ── 片段解析探测（懒构造 + 按 rules_dir 缓存） ──

_probe_cache: dict[str, Callable[[str], bool]] = {}
_ast_cache: dict[str, Callable[[str], tuple]] = {}
_env_cache: dict[str, tuple] = {}


def _build_env(rules_dir: str) -> tuple:
    """构造共享解析环境（rules / selector / lexer / pre_scan 配置），按 rules_dir
    缓存（重复调用幂等，与管线共享组件初始化一致）。"""
    env = _env_cache.get(rules_dir)
    if env is not None:
        return env

    from core.config_registry import ConfigRegistry
    from core.define import GrammarRulesRegister
    from core.plugin_loader import load_all_components
    from lexer import Lexer, load_pre_scan_config
    from parser import setup_grammar
    from parser.rule_selector import RuleSelector

    ConfigRegistry.load_all(
        rules_dir, ext_dirs=None, plugins_dir=os.path.join(rules_dir, "plugins")
    )
    load_all_components()
    rules = setup_grammar(rules_dir, GrammarRulesRegister.get_default(), ext_dirs=None)
    stmt_names = [
        name
        for name, rule in rules.items()
        if hasattr(rule, "has_pass_end_case") and rule.has_pass_end_case()
    ]
    env = (
        rules,
        RuleSelector(rules, stmt_names),
        Lexer(rules_dir=rules_dir),
        load_pre_scan_config(rules_dir),
    )
    _env_cache[rules_dir] = env
    return env


def build_parse_probe(rules_dir: str) -> Callable[[str], bool]:
    """构造"片段能否完整解析"探测函数（懒构造，按 rules_dir 缓存）。

    探测 = 片段作为完整源码走 lexer + parser，无截断/异常 → True。构造过程与管线
    共享组件初始化一致（重复调用幂等）。消费方（阶段 2+）若已有共享组件，可自行
    注入等价 probe，避免重建。
    """
    cached = _probe_cache.get(rules_dir)
    if cached is not None:
        return cached

    rules, selector, lexer, pre_cfg = _build_env(rules_dir)
    from lexer import pre_scan
    from parser import Parser

    def probe(text: str) -> bool:
        try:
            parser = Parser(
                rules_dir=rules_dir,
                pre_symbols=pre_scan(text, pre_cfg),
                rules=rules,
                rule_selector=selector,
                silent=True,
            )
            parser.pre_hints = pre_cfg.get("hints", {})
            ast = parser.parse(lexer.tokenize(text))
        except Exception:  # noqa: BLE001 — 探测语义：任何失败都等于"不可完整解析"
            return False
        return ast is not None and not getattr(parser, "_parse_truncated", False)

    _probe_cache[rules_dir] = probe
    return probe


def build_parse_ast(rules_dir: str) -> Callable[[str], tuple]:
    """构造"片段 → (parser, ast)"解析函数（懒构造 + 缓存，与 probe 共用环境）。"""
    cached = _ast_cache.get(rules_dir)
    if cached is not None:
        return cached

    rules, selector, lexer, pre_cfg = _build_env(rules_dir)
    from lexer import pre_scan
    from parser import Parser

    def parse_ast(text: str) -> tuple:
        parser = Parser(
            rules_dir=rules_dir,
            pre_symbols=pre_scan(text, pre_cfg),
            rules=rules,
            rule_selector=selector,
            silent=True,
        )
        parser.pre_hints = pre_cfg.get("hints", {})
        return parser, parser.parse(lexer.tokenize(text))

    _ast_cache[rules_dir] = parse_ast
    return parse_ast


def _first_child_named(node: Any, name: str) -> Any | None:
    for child in node.iter_children():
        if child.node_name == name:
            return child
    return None


def extract_macro_body(
    body: str, shape_key: str, parse_ast: Callable[[str], tuple], cfg: dict | None = None
) -> Any | None:
    """按包裹配置（`pick` / `skip_head` / `skip_tail`）钻取宏体子树。

    步骤：模板填入宏体 → 解析 → 按 `pick` 节点名路径逐层钻取容器 → 取容器
    children 去掉 `skip_head` 头 / `skip_tail` 尾 → 合成 `MacroBody` 包装节点
    （children = 宏体对应的顶层单元）。失败返回 None。

    提取路径是**语言语法知识**（随包裹模板结构定），由语言包 `[macro_shape.wrappers.
    <key>]` 声明，引擎只做通用钻取。
    """
    from core.define import Node

    wrappers, _ = get_shape_config(cfg)
    spec = wrappers.get(shape_key)
    if not isinstance(spec, dict):
        return None
    tpl = spec.get("tpl") or ""
    pick = spec.get("pick") or ""
    if not tpl or not pick:
        return None

    _, ast = parse_ast(tpl.replace("{b}", body))
    if ast is None:
        return None
    node = ast
    for seg in pick.split("."):
        node = _first_child_named(node, seg)
        if node is None:
            return None

    children = list(node.iter_children())
    head = int(spec.get("skip_head", 0) or 0)
    tail = int(spec.get("skip_tail", 0) or 0)
    kept = children[head : len(children) - tail] if tail else children[head:]
    if not kept:
        return None
    wrap = Node("MacroBody")
    for child in kept:
        wrap.add_sub_node(child)
    return wrap
