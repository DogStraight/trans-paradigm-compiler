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
def c_render(config_loaded):
    """加载 C 包并返回 render(src) → 渲染文本。测试结束恢复 verilog。"""
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

    yield render
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _read(name: str) -> str:
    with open(os.path.join(_SAMPLES, name), encoding="utf-8") as f:
        return f.read()


def _effective_lines(text: str) -> int:
    return len([ln for ln in text.splitlines() if ln.strip()])


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
