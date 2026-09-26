"""tests/languages/c/test_c_render_fidelity.py — C 包**保真度管线闭环**。

照 verilog 的形态（`tests/e2e/test_real_fidelity.py`：difflib 比值 + 结构断言 + 幂等），
但收敛到 C 包自己的样本（`samples/ring_buffer.{h,c}`）：

    源文本 → tokenize → parse → render → 与源比对（比值/行数）
                                      ↘ 再 tokenize/parse/render → 与第一次渲染相同（幂等）

四条判据（缺任一条都不算"闭环"）：

1. **非空**：渲染输出不为空——引擎对缺渲染配置的规则**静默输出空串**，
   只断言"没报错"是抓不到的（这是本包最初 1/70 覆盖率的真实症状）。
2. **结构完整**：渲染行数 ≥ 源文件有效行数的 80%（防"只渲染出一部分"）。
3. **内容保真**：`difflib` 比值 ≥ 0.80（容忍格式化差异，但抓得住内容丢失）。
4. **幂等**：渲染结果再走一遍管线，渲染出的文本与第一遍**逐字相同**。

另有注释判据：源里的 line/block 注释（`/* … */`）必须出现在渲染输出里
——注释按设计以**节点**挂载，缺 `Comment` 规则时会被静默丢弃。
"""

import difflib
import os

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from renderer import Renderer

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")
_SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

# 保真度阈值：格式化差异（空行/缩进规范化）会拉低比值；0.80 足以区分
# "结构完整重排"与"内容丢失/截断"（后者通常 < 0.5）。同 verilog 的取值口径。
_FIDELITY_THRESHOLD = 0.80
_LINE_COVERAGE = 0.80


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """加载 C 包 → {"render": render(src), "tokenize": tokenize(src)}（测试结束恢复 verilog）。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    rules = setup_grammar(_RULES, GrammarRulesRegister(), ext_dirs=[_PLUGINS])
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=_RULES, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=_RULES, ext_dirs=[_PLUGINS])
    renderer = Renderer(rules_dir=_RULES)

    def render(src: str) -> str:
        ast = parser.parse(lexer.tokenize(src))
        return renderer.render(ast)

    yield {"render": render, "tokenize": lexer.tokenize}
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


@pytest.fixture(scope="module")
def c_render(c_env):
    """render(src) → 渲染文本（既有判据用；词法面见 `c_env`）。"""
    return c_env["render"]


def _read(name: str) -> str:
    with open(os.path.join(_SAMPLES, name), encoding="utf-8") as f:
        return f.read()


def _effective_lines(text: str) -> int:
    return len([ln for ln in text.splitlines() if ln.strip()])


# trivia token 前缀（空白/换行/注释）：渲染**允许**重排，序列判据只比显著 token
_TRIVIA_PREFIXES = ("space", "newline", "comment")


def _significant(tokens) -> list[tuple[str, str]]:
    """显著 token 序列 `[(type, content)]`（去 trivia 与注释）。"""
    return [
        (t.type, t.content)
        for t in tokens
        if not t.type.startswith(_TRIVIA_PREFIXES)
    ]


_SAMPLE_NAMES = ["ring_buffer.h", "ring_buffer.c", "edge_comments.c"]


class TestRenderNonEmpty:
    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_sample_renders_non_empty(self, c_render, name):
        """判据 1：渲染输出非空（缺布局会静默输出空串，故这条必须单独存在）。"""
        out = c_render(_read(name))
        assert out.strip(), f"{name} 渲染为空——渲染配置缺失（引擎静默丢内容）"


class TestRenderFidelity:
    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_line_coverage(self, c_render, name):
        """判据 2：渲染行数不低于源文件有效行数的 80%。"""
        src = _read(name)
        out = c_render(src)
        src_lines, out_lines = _effective_lines(src), _effective_lines(out)
        assert out_lines >= src_lines * _LINE_COVERAGE, (
            f"{name}: 渲染 {out_lines} 行 vs 源 {src_lines} 行——结构不完整"
        )

    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_difflib_ratio(self, c_render, name):
        """判据 3：与源文本的 difflib 比值 ≥ 0.80。"""
        src = _read(name)
        out = c_render(src)
        ratio = difflib.SequenceMatcher(None, src, out).ratio()
        assert ratio >= _FIDELITY_THRESHOLD, (
            f"{name}: 保真度 {ratio:.2f} < {_FIDELITY_THRESHOLD}——内容有丢失"
        )


class TestRenderIdempotent:
    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_second_pass_is_identical(self, c_render, name):
        """判据 4：渲染结果再过一遍管线，输出逐字相同。"""
        first = c_render(_read(name))
        second = c_render(first)
        assert first == second, (
            f"{name}: 渲染不幂等（第二遍与第一遍不同）——"
            "说明渲染/解析对同一文本产生了两棵树"
        )


class TestCommentPreservation:
    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_block_comments_survive(self, c_render, name):
        """line/block 注释必须出现（按设计以**节点**挂载；缺 `Comment` 规则会静默丢）。"""
        src = _read(name)
        assert "/*" in src, "样本里应含块注释，否则本用例无意义"
        out = c_render(src)
        # 取源里第一段块注释的正文做锚点（不做全文严格比对，容忍空白规范化）
        start = src.index("/*")
        end = src.index("*/", start)
        anchor = " ".join(src[start + 2 : end].split())[:24]
        assert anchor and anchor in " ".join(out.split()), (
            f"{name}: 块注释正文 {anchor!r} 未出现在渲染输出里（注释被丢弃）"
        )


def _comments(text: str) -> list[str]:
    """提取注释正文（去空白），用于"注释清单"比对。

    只做**形态无关**的正文比对：`/* … */` 与 `// …` 都归一到"去掉定界符与空白后的正文"。
    这样排版变化不影响判据，而"整条注释丢失/被吞进代码"会立刻暴露。
    """
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j
            out.append(" ".join(text[i + 2 : j].split()))
            i = j + 2
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" ".join(text[i + 2 : j].split()))
            i = j + 1
        else:
            i += 1
    return [c for c in out if c]


class TestCommentInventory:
    """**注释清单判据**：源里的每一条注释都必须在渲染输出里出现（数量与正文都对齐）。

    比"抽样锚点"强：抽样只看一条，清单判据能抓住"某一条被静默吞掉"。
    容忍排版（正文去空白后比对），不容忍丢失或与代码混在一起（正文不再相等）。
    """

    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_every_source_comment_survives(self, c_render, name):
        src = _read(name)
        out = c_render(src)
        want, got = _comments(src), _comments(out)
        assert len(got) >= len(want), (
            f"{name}: 源 {len(want)} 条注释，渲染只剩 {len(got)} 条（注释被丢弃）\n"
            f"缺: {[c[:24] for c in want if c not in got][:5]}"
        )
        missing = [c for c in want if c not in got]
        assert not missing, (
            f"{name}: 以下注释未出现在渲染输出：{[c[:30] for c in missing]}"
        )


class TestTokenSequence:
    """**判据 7：显著 token 序列保真**——渲染前后逐项相同 `[(type, content)]`。

    "原文打印"的强判据：重排只许动空白，**不许动 token 的序**。比 `difflib` 强
    （`i++` → `++i` 只差 3 个字符、比值 0.99+，`difflib` 与行数判据都抓不到），
    也比"清单比对"贴题（清单管有没有，序列管顺序对不对）。

    语言无关：两侧都用包自己的 lexer；trivia（`space.*` / 注释）不参与比对
    ——排版允许重排，注释另有清单判据。
    """

    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_significant_tokens_identical(self, c_env, name):
        src = _read(name)
        out = c_env["render"](src)
        want = _significant(c_env["tokenize"](src))
        got = _significant(c_env["tokenize"](out))
        assert got == want, _token_diff(name, want, got)

    @pytest.mark.parametrize("name", _SAMPLE_NAMES)
    def test_significant_tokens_round_trip(self, c_env, name):
        """再渲染一遍仍逐项相同（与判据 4 同源，按 token 面再确认一次）。"""
        first = c_env["render"](_read(name))
        second = c_env["render"](first)
        assert _significant(c_env["tokenize"](second)) == _significant(
            c_env["tokenize"](first)
        ), _token_diff(name, _significant(c_env["tokenize"](first)),
                       _significant(c_env["tokenize"](second)))


def _token_diff(name: str, want: list, got: list) -> str:
    """token 序列差异的可读报告（首个不同的窗口 + 长度差）。"""
    for i, (w, g) in enumerate(zip(want, got)):
        if w != g:
            return (
                f"{name}: 显著 token 序列在第 {i} 项起不同（渲染动了 token 的序）\n"
                f"  源: {want[max(0, i - 3) : i + 4]}\n"
                f"  出: {got[max(0, i - 3) : i + 4]}"
            )
    return (
        f"{name}: token 数量不同（源 {len(want)} / 出 {len(got)}）——"
        f"多出 {want[len(got):][:5]} / 缺失 {got[len(want):][:5]}"
    )


class TestPostfixOrder:
    """后缀自增/自减的**顺序**判据（pratt `UnaryOp` 前缀/后缀同名，由 `when` 分发）。

    缺陷（本包首例，2026-09-25）：布局原语无"按属性值换序"能力，只能二选一 →
    `i++` 渲成 `++i`（token 齐全、**顺序反了**）。C 里 `i++` 与 `++i` 语义不同，
    故这是**语义级**保真缺陷；而 `difflib` 只差 3 个字符（比值 0.99+）、行数判据
    也看不出，两者都抓不到——单列顺序判据，并由判据 7（token 序列）在样本面上兜底。
    """

    _SRC = "int f(int n) {\n    int i = 0;\n    i++;\n    n--;\n    return i;\n}\n"

    def test_postfix_stays_postfix(self, c_render):
        out = c_render(self._SRC)
        assert "i++;" in out and "n--;" in out, f"后缀自增/自减丢失：\n{out}"
        assert "++i" not in out and "--n" not in out, f"后缀被渲成前缀（顺序反了）：\n{out}"

    def test_prefix_stays_prefix(self, c_render):
        """反向：前缀不得被渲成后缀（`when` 的 else 支）。"""
        out = c_render("int f(int x) {\n    return -x;\n}\n")
        assert "-x" in out and "x-" not in out, out

    def test_round_trip(self, c_render):
        out = c_render(self._SRC)
        assert c_render(out) == out, f"渲染不幂等：\n{out}\n---\n{c_render(out)}"


# 同一位置领到**多条**独占行注释：源序必须保住（枚举体首项前是最小复现面）。
_HEAD_COMMENT_ORDER_SRC = (
    "enum color {\n"
    "    // 第一行\n"
    "    // 第二行\n"
    "    RED\n"
    "};\n"
)


class TestHeadCommentOrder:
    """**首注释源序判据**：同一位置领到的多条独占行注释，渲染顺序须与源一致。

    缺陷（2026-09-25 实测）：`_insert_gap_comments` 按行升序遍历却逐条
    `insert(0, …)` → 两条连续注释进 AST 就是**倒序**，渲出「后一行在前」；
    产物再解析又回到源序 ⇒ 二次渲染与首渲染不同（渲染不幂等）。顺序与幂等
    两条一起守：只守其中一条时，"倒序但恰好往返一致"的实现仍可能漏过。
    """

    def test_source_order_preserved(self, c_render):
        out = c_render(_HEAD_COMMENT_ORDER_SRC)
        assert "// 第一行" in out and "// 第二行" in out, f"注释丢失：{out!r}"
        assert out.index("// 第一行") < out.index("// 第二行"), (
            f"首注释被倒序（源：第一行在前）:\n{out}"
        )

    def test_round_trip_after_reorder(self, c_render):
        out = c_render(_HEAD_COMMENT_ORDER_SRC)
        assert c_render(out) == out, f"渲染不幂等:\n{out}\n---\n{c_render(out)}"
