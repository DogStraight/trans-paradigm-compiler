"""轻量预扫描 — 在 Lexer 阶段收集顶层声明符号。

只识别单文件内的顶层声明名，不处理 import/pkg 等跨文件引用。
预扫描不是精确的——漏掉的声明名只是让 parser 多试几条规则而已。

配置由 ConfigRegistry 声明式加载，不再内部 try/except 吞错误。

用法:
    from lexer.pre_scan import pre_scan, load_pre_scan_config
    config = load_pre_scan_config(rules_dir)
    symbols = pre_scan(source_code, config)
Doc: docs/language_walkthrough.md（预扫描：顶层声明收集）
"""

import re
from core.config_registry import declare_cfg

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# lexer.pre_scan
#   #sym:config = [pre_scan]
#   格式: dict
#     { context_keywords: list[str],
#       decl: { kind: { keyword, ... }, ... },
#       clean: [ { kind, start, end? }, ... ] }
# clean 条目声明预扫描前的源文本清理形态（注释/字符串剥离）——
# 语言知识（//、/* */、" 等形态）在配置，引擎不硬编码。
_pre_scan_cfg: dict = declare_cfg("lexer.pre_scan", {}, __name__, "_pre_scan_cfg")


# ── 编译缓存 ──
_CACHE: dict[str, dict] = {}


def load_pre_scan_config(rules_dir: str | None = None) -> dict:
    """从 ConfigRegistry 获取预扫描配置并编译。

    Args:
        rules_dir: 规则目录；非 None 时兼作 _CACHE 缓存键，并按该语言包
            自包含解析（同 Lexer：不依赖最后一次 load_all 的全局状态——
            同一进程跨语言时不会串用上一语言的 pre_scan 配置。yaml 未
            声明 pre_scan → 空配置，不残留 verilog 的 decl/clean 规则）。

    Returns:
        编译后的配置字典，可直接传入 pre_scan()。
    """
    if rules_dir is not None and rules_dir in _CACHE:
        return _CACHE[rules_dir]

    if rules_dir:
        # 按语言包自包含解析（与 Lexer.__init__ 同模式）
        from core.config_registry import ConfigRegistry
        import os

        resolved = ConfigRegistry.resolve(
            rules_dir,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        raw = dict(resolved.get("lexer.pre_scan", {}) or {})
    else:
        raw = dict(_pre_scan_cfg)

    result = _compile(raw, rules_dir)
    if rules_dir is not None:
        _CACHE[rules_dir] = result
    return result


def _build_clean_regex(entry: dict) -> tuple[re.Pattern, str] | None:
    """将一条 [[pre_scan.clean]] 声明编译为 (正则, 替换串) 对。

    语言无关：只做通用形态→正则的映射（语言知识在配置）。
      kind = "line"   → start 到行尾
      kind = "block"  → start 到 end（可跨行）
      kind = "string" → start 定界符到配对定界符（不跨行），替换为
                        定界符对（避免两侧词粘连，如 module "x"( 中
                        字符串被空串替换后 module 与 ( 不会拼词）
    """
    kind = entry.get("kind")
    start = entry.get("start", "")
    if not isinstance(start, str) or not start:
        return None
    if kind == "line":
        return re.compile(re.escape(start) + r"[^\n]*"), ""
    if kind == "block":
        end = entry.get("end", "")
        if not isinstance(end, str) or not end:
            return None
        return (
            re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL),
            "",
        )
    if kind == "string":
        esc = re.escape(start)
        return (
            re.compile(esc + r"[^" + esc + r"\n]*" + esc),
            start + start,
        )
    return None


def _compile(config: dict, rules_dir: str | None = None) -> dict:
    """将 TOML 配置编译为正则模式。"""
    context_kws = frozenset(config.get("context_keywords", []))
    decls = config.get("decl", {})

    patterns: list[tuple[str, re.Pattern]] = []
    hints: dict[str, list[str]] = {}
    for kind, cfg in decls.items():
        keyword = cfg.get("keyword", "")
        capture = cfg.get("name_capture", "next_word")
        terminators = cfg.get("terminators", [])
        skip_kws = cfg.get("skip_keywords", [])
        pat = _build_regex(keyword, capture, skip_kws, terminators)
        if pat:
            patterns.append((kind, re.compile(pat)))
        # 规则选择提示
        rh = cfg.get("rule_hints", [])
        if rh:
            hints[kind] = rh

    all_kws = "|".join(cfg.get("keyword", "") for cfg in decls.values())
    fallback = re.compile(rf"\b({all_kws})\s+(\w+)") if all_kws else None

    # 源文本清理正则（[[pre_scan.clean]]，配置驱动——无声明则空列表不清理）
    clean_patterns: list[tuple[re.Pattern, str]] = []
    for entry in config.get("clean", []) or []:
        if not isinstance(entry, dict):
            continue
        built = _build_clean_regex(entry)
        if built is not None:
            clean_patterns.append(built)

    result = {
        "patterns": patterns,
        "fallback": fallback,
        "context_keywords": context_kws,
        "hints": hints,
        "clean_patterns": clean_patterns,
    }
    if rules_dir is not None:
        _CACHE[rules_dir] = result
    return result


def _build_regex(
    keyword: str,
    capture: str,
    skip_keywords: list[str],
    terminators: list[str],
) -> str:
    """为一种声明类别构建匹配正则，首个分组为声明名。"""
    term_escaped = [re.escape(t) for t in terminators]
    term_class = f"[{''.join(term_escaped)}]" if term_escaped else ""

    if capture == "next_word":
        skip = "".join(rf"(?:{kw}\s+)?" for kw in skip_keywords)
        base = rf"\b{keyword}\s+{skip}(\w+)"
        return rf"{base}\s*(?:{term_class})" if term_class else base

    elif capture == "after_range":
        skip = "".join(rf"(?:{kw}\s+)?" for kw in skip_keywords)
        return rf"\b{keyword}\s+{skip}(?:\[[^\]]*\]\s+)?(\w+)\s*\("

    elif capture == "last_word_before_semicolon":
        return rf"\b{keyword}\s+.*?(\w+)\s*;"

    return ""


# ── 文本预处理 ──
# 清理形态（注释/字符串）由配置声明（[[pre_scan.clean]]）构建，引擎不
# 硬编码任何语言的注释/字符串形态。


def _clean_text(text: str, clean_patterns: list) -> str:
    for pattern, replacement in clean_patterns:
        text = pattern.sub(replacement, text)
    return text


def _is_decl_name(name: str, context_kws: frozenset) -> bool:
    return not (name in context_kws or name.startswith("$"))


def pre_scan(
    text: str,
    config: dict | None = None,
) -> dict[str, str]:
    """快速扫描文本，收集顶层声明名 → 类别 的映射。

    Args:
        text: 源代码文本
        config: load_pre_scan_config() 返回的编译后配置。
                None 时使用默认配置（回退自动加载）。

    Returns:
        { "decl_name": "module" | "interface" | "function" | "task" | "typedef", ... }
    """
    if config is None:
        config = load_pre_scan_config()

    patterns = config.get("patterns", [])
    fallback = config.get("fallback")
    context_kws = config.get("context_keywords", frozenset())
    clean_patterns = config.get("clean_patterns", [])

    cleaned = _clean_text(text, clean_patterns)
    sym: dict[str, str] = {}

    for kind, pattern in patterns:
        for m in pattern.finditer(cleaned):
            name = m.group(1)
            if not _is_decl_name(name, context_kws):
                continue
            if name not in sym:
                sym[name] = kind

    if fallback:
        for m in fallback.finditer(cleaned):
            kind, name = m.group(1), m.group(2)
            if not _is_decl_name(name, context_kws):
                continue
            if name not in sym:
                sym[name] = kind

    return sym
