"""number_gen.py — 数字形态声明 → FSM 转移表生成器

将语言包声明的数字形态（TOML）编译为 GenericFSM 使用的转移表 + 接受状态。

声明格式（片段式，贴近 IEEE 1364-2005 A.8.7 统一骨架 `[size] base value`）：

    [[number.based]]
    name = "verilog_width"        # 可选，调试用
    size = { digits = "nonzero" } # size 形态：nonzero=非零开头 / none=无 size
    base_prefix = "'"             # 引号（可含可选的 s）
    bases = ["d", "b", "o", "h"]  # 进制字母
    value_digits = { d = "dec", b = "bin", o = "oct", h = "hex" }
    value_allow = ["x", "z", "?"] # 基值中允许的特殊字符
    value_allow_space = true      # 基值前允许空格（如 32'h ffff_ffff）

    [[number.based]]
    name = "c_hex"
    size = "none"
    base_prefix = "0x|0b|0o"      # C 风格前缀
    bases = []                    # 无进制字母，值随前缀
    value_digits = { x = "hex", b = "bin", o = "oct" }
    value_allow = []

    [[number.real]]
    name = "float"
    # 浮点/科学计数：dec [. dec] [e[+-] dec]（C 风格）

语言无关引擎：本生成器不感知任何语言，只把声明编译成表。
"""

from __future__ import annotations

# ── 数字形态状态基类 ──
# 状态模型：每种形态编译出 (size→base→value) 的链式状态；
# 多个形态共享同一套通用字符类别（dec/bin/oct/hex 等）。

# 通用字符类别函数（与语言无关：数字/字母/符号的归类）
# 注意：base 字母（d/b/o/h）用独立类别（base_d/base_b/base_o/base_h），
# 与 value 中的 hex 字母（hex_b/hex_d/hex_e）区分——同一字符在 base 位置
# 是进制字母，在 value 位置是十六进制 digit，类别必须不同。
_CHAR_CATEGORY: dict[str, str] = {
    "0": "digit0", "1": "digit1", "2": "digit2", "3": "digit3",
    "4": "digit4", "5": "digit5", "6": "digit6", "7": "digit7",
    "8": "digit8", "9": "digit9",
    "d": "base_d", "D": "base_d",
    "b": "base_b", "B": "base_b",
    "o": "base_o", "O": "base_o",
    "h": "base_h", "H": "base_h",
    "s": "sign_s", "S": "sign_s",
    # hex value digit：a/b/c/d/f（b/d 既是 base 字母也是 hex digit——
    # 在 value 位置由 hex_value_b/hex_value_d 类别识别，与 base 位置区分；
    # e 保持 eE 类别——它同时是指数标记和 hex digit，两种位置共用）
    "a": "hex_value_abc", "c": "hex_value_abc", "f": "hex_value_abc",
    "b": "hex_value_b", "d": "hex_value_d",
    "A": "hex_value_abc", "C": "hex_value_abc", "F": "hex_value_abc",
    "B": "hex_value_b", "D": "hex_value_d",
    "e": "eE", "E": "eE",
    "x": "xz", "X": "xz", "z": "xz", "Z": "xz", "?": "xz",
    "_": "underscore", ".": "dot", "'": "quote", "+": "sign", "-": "sign",
}


def char_category(ch: str) -> str | None:
    """全局字符类别函数（数字形态通用）。"""
    return _CHAR_CATEGORY.get(ch)


class NumberPattern:
    """单个数字形态模式：由声明编译出的状态链。

    状态空间独立编号（每个 pattern 有自己的起始/接受状态），
    run() 时从本 pattern 的起始态开始走。
    """

    def __init__(
        self,
        name: str,
        transitions: dict[tuple[int, str], int],
        accepting: set[int],
        start_state: int,
        base_states: dict[str, int] | None = None,
        allow_space_after_quote: bool = False,
    ):
        self.name = name
        self.transitions = transitions
        self.accepting = accepting
        self.start_state = start_state
        self.base_states = base_states or {}   # 进制字母 → value 态
        self.allow_space_after_quote = allow_space_after_quote


def _digit_cats_for(radix: str) -> set[str]:
    """进制 → 该进制合法 digit 的字符类别集。"""
    if radix == "hex":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "digit8", "digit9",
                "hex_value_abc", "hex_value_b", "hex_value_d", "eE",
                "xz"}
    if radix == "dec":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "digit8", "digit9", "xz"}
    if radix == "bin":
        return {"digit0", "digit1", "xz"}
    if radix == "oct":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "xz"}
    return set()


def _expand_prefix(prefix: str) -> list[str]:
    """展开带 | 的前缀串（如 "0x|0b" → ["0x", "0b"]）。"""
    return [p for p in prefix.split("|") if p]


def compile_number_pattern(cfg: dict) -> NumberPattern:
    """编译单个 [[number.based]] 声明为 NumberPattern。"""
    name = cfg.get("name", "based")
    transitions: dict[tuple[int, str], int] = {}
    accepting: set[int] = set()
    sid = [0]
    base_states: dict[str, int] = {}

    def new_state() -> int:
        s = sid[0]
        sid[0] += 1
        return s

    size_cfg = cfg.get("size", "none")
    base_prefix = cfg.get("base_prefix", "'")
    bases = cfg.get("bases", [])
    value_digits = cfg.get("value_digits", {})
    value_allow = cfg.get("value_allow", [])
    allow_space = cfg.get("value_allow_space", False)
    # 无前缀形态（base_prefix = "none"）：size 态即最终接受态（十进制整数/浮点），
    # 不建 quote/base 链
    no_prefix = base_prefix == "none"

    # ── size 部分 ──
    size_is_none = size_cfg == "none" or (
        isinstance(size_cfg, dict) and size_cfg.get("digits") == "none"
    )
    # 无前缀十进制形态是否允许 0 开头（0 / 017 / 0.5，verilog unsigned_number）：
    # 由 size.digits = "any" 显式声明；默认 nonzero 严格 digit1-9 开头
    # （C 风格：0 开头交给 c_octal 这类前缀形态，避免 08 被吞成十进制）
    size_allow_zero = (
        isinstance(size_cfg, dict) and size_cfg.get("digits") == "any"
    )
    start = new_state()

    if size_is_none:
        # 无 size：直接进 base_prefix
        current = start
    else:
        # 有 size：size 语义 = non_zero_unsigned_number（IEEE A.8.7，
        # non_zero_decimal_digit 开头）——带前缀形态只 digit1-9 开头（0'b1 非法）；
        # 无前缀形态按 size_allow_zero 决定 0 开头（verilog_dec = any；c_dec = nonzero）
        size_state = new_state()
        if no_prefix and size_allow_zero:
            for i in range(0, 10):
                transitions[(start, f"digit{i}")] = size_state
        else:
            for i in range(1, 10):
                transitions[(start, f"digit{i}")] = size_state
        for i in range(0, 10):
            transitions[(size_state, f"digit{i}")] = size_state
        transitions[(size_state, "underscore")] = size_state
        # 浮点/科学计数：dec [. dec] [e[+-] dec]（旧 FSM DEC_INT 行为）
        frac_state = new_state()          # 小数点后（3.14）
        exp_state = new_state()           # e 之后（1e10）
        exp_sign_state = new_state()      # e+ / e- 符号后
        exp_digit_state = new_state()     # 指数数字
        transitions[(size_state, "dot")] = frac_state
        transitions[(size_state, "eE")] = exp_state
        for i in range(0, 10):
            transitions[(frac_state, f"digit{i}")] = frac_state
        transitions[(frac_state, "underscore")] = frac_state
        transitions[(frac_state, "eE")] = exp_state
        accepting.add(frac_state)
        transitions[(exp_state, "sign")] = exp_sign_state
        for i in range(0, 10):
            transitions[(exp_state, f"digit{i}")] = exp_digit_state
        for i in range(0, 10):
            transitions[(exp_sign_state, f"digit{i}")] = exp_digit_state
        for i in range(0, 10):
            transitions[(exp_digit_state, f"digit{i}")] = exp_digit_state
        transitions[(exp_digit_state, "underscore")] = exp_digit_state
        accepting.add(exp_digit_state)
        # size 态本身是接受态：十进制整数（7 / 123 / 0 等）
        accepting.add(size_state)
        current = size_state

    # ── base_prefix 部分 ──
    # 无前缀形态（base_prefix="none"）：size 态即接受态，直接返回
    if no_prefix:
        return NumberPattern(
            name, transitions, accepting, start, base_states, allow_space
        )

    # 前缀可能是多字符（0x/0b/0o）或单字符（' / 0）
    prefixes = _expand_prefix(base_prefix)
    # 多字符前缀：每条前缀独立建链，值随前缀（value_digits 键 = 前缀末字符）
    if prefixes and any(len(p) > 1 for p in prefixes):
        # 按首字符分组的链（0x/0b/0o 首字符都是 0）
        by_first: dict[str, list[str]] = {}
        for p in prefixes:
            by_first.setdefault(p[0], []).append(p)
        for first, plist in by_first.items():
            if first not in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                continue
            # 前缀以数字开头（0x）：从 size/start 的 digit{first} 转移
            from_state = start if size_is_none else current
            node = transitions.get((from_state, f"digit{first}"))
            if node is None:
                node = new_state()
                transitions[(from_state, f"digit{first}")] = node
            for p in plist:
                # 每条前缀独立建链（0x → xz；0b → base_b；…）
                cur = node
                ok = True
                for ch in p[1:]:
                    cat = _CHAR_CATEGORY.get(ch)
                    if cat is None:
                        ok = False
                        break
                    nxt = new_state()
                    transitions[(cur, cat)] = nxt
                    cur = nxt
                if not ok:
                    continue
                # 前缀末字符决定 value 进制（value_digits: {x:"hex", b:"bin", …}）
                radix = value_digits.get(p[-1].lower(), "dec")
                for cat in _digit_cats_for(radix):
                    if cat == "xz":
                        continue  # 多字符前缀形态暂不支持 x/z value
                    transitions[(cur, cat)] = cur
                transitions[(cur, "underscore")] = cur
                accepting.add(cur)
        return NumberPattern(
            name, transitions, accepting, start, base_states, allow_space
        )

    # ── 单字符前缀（' / 0 / 's）──
    # 前缀首字符类别按声明（' → quote，0 → digit0），不再硬编码 quote——
    # 支持 c4 前导 0 八进制（base_prefix = "0"）
    quote_state = new_state()
    signed_opt = cfg.get("signed", False)
    prefix_first = base_prefix[0] if base_prefix and base_prefix != "none" else "'"
    prefix_cat = _CHAR_CATEGORY.get(prefix_first, "quote")
    if signed_opt:
        # 先前缀（quote/digit0）到 quote_state，再 s（sign_s）到 sign_after_state
        transitions[(current, prefix_cat)] = quote_state
        sign_after_state = new_state()
        transitions[(quote_state, "sign_s")] = sign_after_state
    else:
        transitions[(current, prefix_cat)] = quote_state
        sign_after_state = quote_state

    # ── base 字母 → value 态（或前缀后直接 value）──
    if bases:
        for base_char in bases:
            base_lower = base_char.lower()
            radix = value_digits.get(base_lower, "dec")
            value_state = new_state()
            base_states[base_lower] = value_state
            cat = _CHAR_CATEGORY.get(base_char)
            if cat:
                transitions[(sign_after_state, cat)] = value_state
            # value 态：进制 digit 集 + 允许的特殊字符
            for cat in _digit_cats_for(radix):
                if cat == "xz" and "x" not in value_allow and "z" not in value_allow and "?" not in value_allow:
                    continue  # x/z/? 只在声明允许时进 value
                transitions[(value_state, cat)] = value_state
            transitions[(value_state, "underscore")] = value_state
            accepting.add(value_state)
    else:
        # 无 base 字母：前缀后直接进 value（值随前缀，value_digits 键 = 前缀末字符）
        # 如 c4 前导 0 八进制：base_prefix = "0"，value_digits = { "0" = "oct" }
        radix = value_digits.get(base_prefix[-1].lower(), "dec")
        for cat in _digit_cats_for(radix):
            if cat == "xz" and "x" not in value_allow and "z" not in value_allow and "?" not in value_allow:
                continue
            transitions[(sign_after_state, cat)] = sign_after_state
        transitions[(sign_after_state, "underscore")] = sign_after_state
        accepting.add(sign_after_state)

    return NumberPattern(
        name, transitions, accepting, start, base_states, allow_space
    )


# ── 编译声明列表 ──


def compile_patterns(cfg_list: list[dict]) -> list[NumberPattern]:
    """编译 [[number.based]] 声明列表。"""
    return [compile_number_pattern(c) for c in cfg_list]
