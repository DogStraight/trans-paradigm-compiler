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
from bisect import bisect_right

from core.config_registry import declare_cfg
from core.errors import ConfigError

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# lexer.pre_scan
#   #sym:config = [pre_scan]
#   格式: dict
#     { context_keywords: list[str],
#       fallback: bool,                       # 默认 true
#       decl: { kind: { keyword, ... }, ... },
#       clean: [ { kind, start, end? }, ... ] }
# clean 条目声明预扫描前的源文本清理形态（注释/字符串剥离）——
# 语言知识（//、/* */、" 等形态）在配置，引擎不硬编码。
# fallback（默认 true）声明"声明类别之外的关键字也按 `\b(kw)\s+(\w+)` 兜底收集"：
# 该兜底会带入 `int foo` 这类**非声明名**（`foo` 可能只是类型词后的普通词），
# 只对"粗提示"用途安全；需要干净符号面（如按 phase 对比、消费方据名判定）的语言包
# 应显式 `fallback = false`——声明类别（`[pre_scan.decl.*]`）的收集**不受它影响**。
# decl 条目可另声明两个**语义面**（引擎只搬运、不解释）：
#   type_name = true        # 该类 kind 算"类型名命名空间"（如 typedef；tag_* 不声明）
#   trial_as  = "<token 型>" # 该类名的"类型名形态"试解析替换 token 型（需要
#                           # type_name=true 时必填；非 bool/缺 trial_as ⇒ fail-fast）
# 二者供消费方（linter 资格判定）使用：语言知识在配置，引擎不硬编码任何 kind 名。
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
    type_name_kinds: set[str] = set()
    trial_as: dict[str, str] = {}
    for kind, cfg in decls.items():
        keyword = cfg.get("keyword", "")
        capture = cfg.get("name_capture", "next_word")
        terminators = cfg.get("terminators", [])
        skip_kws = cfg.get("skip_keywords", [])
        pat = _build_regex(keyword, capture, skip_kws, terminators)
        if pat:
            patterns.append((kind, re.compile(pat)))
        # 类型名语义面（消费方按 kind 过滤；引擎不解释语义）：声明了 type_name 的
        # 类别必须同时给出"类型名形态"试解析替换 token 型（fail-fast，不静默降级）。
        type_name = cfg.get("type_name", False)
        if not isinstance(type_name, bool):
            raise ConfigError(
                f"[pre_scan.decl.{kind}] type_name 必须是布尔（true/false），"
                f"收到 {type_name!r}"
            )
        if type_name:
            probe = cfg.get("trial_as")
            if not isinstance(probe, str) or not probe:
                raise ConfigError(
                    f"[pre_scan.decl.{kind}] 声明了 type_name = true，"
                    "必须同时声明 trial_as = \"<类型名形态 token 型>\"（试解析替换用）"
                )
            type_name_kinds.add(kind)
            trial_as[kind] = probe

    all_kws = "|".join(cfg.get("keyword", "") for cfg in decls.values())
    # fallback = 声明类别之外的关键字是否也兜底收集（默认 true）；非 bool ⇒ fail-fast
    use_fallback = config.get("fallback", True)
    if not isinstance(use_fallback, bool):
        raise ConfigError(
            f"[pre_scan] fallback 必须是布尔（true/false），收到 {use_fallback!r}"
        )
    fallback = re.compile(rf"\b({all_kws})\s+(\w+)") if (use_fallback and all_kws) else None

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
        "clean_patterns": clean_patterns,
        # 类型名语义面（供消费方按 kind 过滤 / 取试解析替换 token 型）
        "type_name_kinds": frozenset(type_name_kinds),
        "trial_as": trial_as,
    }
    if rules_dir is not None:
        _CACHE[rules_dir] = result
    return result


def _regex_next_word(keyword: str, skip_keywords: list[str], term_class: str) -> str:
    """关键字后下一个词（可跨过修饰词）；声明了终结符集则要求其后紧跟终结符。"""
    skip = "".join(rf"(?:{kw}\s+)?" for kw in skip_keywords)
    base = rf"\b{keyword}\s+{skip}(\w+)"
    return rf"{base}\s*(?:{term_class})" if term_class else base


def _regex_after_range(keyword: str, skip_keywords: list[str]) -> str:
    """跨过可选位宽范围后的首个词（后随 `(`）——如函数/任务名。"""
    skip = "".join(rf"(?:{kw}\s+)?" for kw in skip_keywords)
    return rf"\b{keyword}\s+{skip}(?:\[[^\]]*\]\s+)?(\w+)\s*\("


def _regex_last_word_before_semicolon(keyword: str) -> str:
    """分号前最后一个词——如 `typedef ... name;`。"""
    return rf"\b{keyword}\s+.*?(\w+)\s*;"


def _build_regex(
    keyword: str,
    capture: str,
    skip_keywords: list[str],
    terminators: list[str],
) -> str:
    """为一种声明类别构建匹配正则，首个分组为声明名。

    capture 形态 → 构造器：`next_word`（词后面可跟终结符集）/ `after_range`
    （跨过可选 `[...]` 位宽）/ `last_word_before_semicolon`；未声明形态 → 空串。
    """
    term_escaped = [re.escape(t) for t in terminators]
    term_class = f"[{''.join(term_escaped)}]" if term_escaped else ""

    if capture == "next_word":
        return _regex_next_word(keyword, skip_keywords, term_class)
    if capture == "after_range":
        return _regex_after_range(keyword, skip_keywords)
    if capture == "last_word_before_semicolon":
        return _regex_last_word_before_semicolon(keyword)
    return ""


# ── 文本预处理 ──
# 清理形态（注释/字符串）由配置声明（[[pre_scan.clean]]）构建，引擎不
# 硬编码任何语言的注释/字符串形态。


def _clean_text(text: str, clean_patterns: list) -> str:
    for pattern, replacement in clean_patterns:
        text = pattern.sub(replacement, text)
    return text


class _CleanMap:
    """按序清理文本 + 记录每遍替换，`original(cleaned_offset)` 逐遍反查回原文。

    只记**替换区间**（注释/字符串段），不建逐字符映射表——tv80_core（4755 行）实测
    逐字符表版本让 `tpc lint` 慢 +13.7%，段表版回到噪声内。反查成本 =
    O(遍数 × log(每遍替换数))，与文本长度无关。
    每遍记录一条：`(cleaned_start, cleaned_end, orig_start, orig_end, repl_len)`。
    """

    def __init__(self) -> None:
        self._passes: list[list[tuple[int, int, int, int, int]]] = []

    def apply(self, text: str, pattern: re.Pattern, replacement: str) -> str:
        out: list[str] = []
        records: list[tuple[int, int, int, int, int]] = []
        cursor = 0
        cleaned_len = 0
        for m in pattern.finditer(text):
            head = text[cursor : m.start()]
            out.append(head)
            cleaned_len += len(head)
            out.append(replacement)
            records.append(
                (cleaned_len, cleaned_len + len(replacement), m.start(), m.end(), len(replacement))
            )
            cleaned_len += len(replacement)
            cursor = m.end()
        out.append(text[cursor:])
        self._passes.append(records)
        return "".join(out)

    def original(self, offset: int) -> int:
        """cleaned 偏移 → 原文偏移（逐遍逆序反查；替换段内映射到段首）。"""
        pos = offset
        for records in reversed(self._passes):
            starts = [r[0] for r in records]
            idx = bisect_right(starts, pos) - 1
            if idx < 0:
                continue  # 该遍此位置之前无替换 ⇒ 偏移不变
            c_start, c_end, o_start, o_end, repl_len = records[idx]
            if pos < c_start:
                continue
            if pos >= c_end:
                pos += (o_end - o_start) - repl_len
                continue
            return o_start if repl_len else o_start  # 替换段内（含空替换）映射到段首
        return pos


def _clean_text_mapped(
    text: str, clean_patterns: list
) -> tuple[str, _CleanMap]:
    """`_clean_text` 的同序同替换版本，额外返回可反查原文的 `_CleanMap`。

    逐模式顺序应用（与 `_clean_text` 完全一致，保证收集结果同口径）；注释/字符串
    清理会删改长度（块注释可跨行）⇒ 行号必须靠映射回原文，不能在 cleaned 上数换行。
    """
    current = text
    cmap = _CleanMap()
    for pattern, replacement in clean_patterns:
        current = cmap.apply(current, pattern, replacement)
    return current, cmap


def _is_decl_name(name: str, context_kws: frozenset) -> bool:
    return not (name in context_kws or name.startswith("$"))


def _brace_depth(text: str, offset: int) -> int:
    """`{`/`}` 深度：文本前 `offset` 个字符里 `{` 数减 `}` 数（下限 0）。

    只数**字符** `{`/`}`（与 `core/utils.square_bracket_types` 同判据：字符是词法
    数据，不依赖配对命名）。调用方传的是**已清理**文本（`clean` 已剥注释/字符串），
    故串内花括号不会误计。深度供"声明顺序"判据的**作用域守卫**用：块内声明
    （`void f(void){ typedef int t; }`）不得给块外使用点（`x = (t)y;`）发资格。
    """
    depth = 0
    for ch in text[: max(offset, 0)]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
    return depth


def _collect_symbols(
    text: str, config: dict, *, with_lines: bool
) -> dict[str, dict]:
    """共用收集循环：`{name: {"kind": ..., "line": ..., "column": ..., "depth": ...}}`。

    `pre_scan()` 与 `pre_scan_with_lines()` 同口径走这里——单一实现，避免两份
    "首见归属/上下文关键词过滤"逻辑漂移。`with_lines=True` 时行号 = **原文**
    1-based 行（经清理偏移映射回原文，不猜、不在 cleaned 上数换行），`depth` =
    该声明名之前的 `{`/`}` 深度（**清理后**文本上计）。
    """
    context_kws = config.get("context_keywords", frozenset())
    cmap: _CleanMap | None = None
    if with_lines:
        cleaned, cmap = _clean_text_mapped(text, config.get("clean_patterns", []))
    else:
        cleaned = _clean_text(text, config.get("clean_patterns", []))

    out: dict[str, dict] = {}

    def add(name: str, kind: str, offset: int) -> None:
        if not _is_decl_name(name, context_kws) or name in out:
            return
        line: int | None = None
        column: int | None = None
        if cmap is not None:
            orig = cmap.original(offset)
            line = text.count("\n", 0, orig) + 1
            column = orig - text.rfind("\n", 0, orig) - 1
        out[name] = {
            "kind": kind,
            "line": line,
            "column": column,
            "depth": _brace_depth(cleaned, offset),
        }

    for kind, pattern in config.get("patterns", []):
        for m in pattern.finditer(cleaned):
            add(m.group(1), kind, m.start(1))
    fallback = config.get("fallback")
    if fallback:
        for m in fallback.finditer(cleaned):
            add(m.group(2), m.group(1), m.start(2))
    return out


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
    return {
        name: rec["kind"] for name, rec in _collect_symbols(text, config, with_lines=False).items()
    }


def pre_scan_with_lines(
    text: str,
    config: dict | None = None,
) -> dict[str, dict]:
    """**并行读取面**（带声明位置）：`{name: {"kind":..., "line":..., "column":...}}`。

    与 `pre_scan()` 同一次收集口径（首见归属、同序清理、同过滤），只是额外给出
    声明名在**原文**中的 1-based 行与 0-based 列——供消费方做"声明顺序敏感"判定
    （如 linter 要求声明位置 ≤ 使用位置）。行号必须经清理偏移映射回原文：注释清理
    会删改长度（块注释可跨行），在 cleaned 文本上数换行会漂移。

    ⚠ **同行声明**（`x=(t)y; typedef int t;`）只比行号分不出先后 ⇒ 同时给
    `column`，调用方按 `(line, column)` 字典序比较（行号不够，实测反例 7）。

    ⚠ 既有 `pre_scan()` 的签名/行为**不变**（本函数是新增面，旧调用方零影响）。
    """
    if config is None:
        config = load_pre_scan_config()
    return _collect_symbols(text, config, with_lines=True)
