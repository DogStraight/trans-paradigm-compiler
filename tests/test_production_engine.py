"""Parser production engine 单元测试 — 合成 Token，不加载 TOML 规则。

直接调用 parser/_production.py 中的 _parse_* 函数，
通过伪造最小 self 对象模拟 Parser 上下文。
"""

import pytest
from core.define import Node, Token, GrammarRule
from parser.parser_core import ParseContext
from parser._production import (
    process_production_node,
    parse_token,
    parse_seq,
    parse_choice,
    parse_repeat,
    parse_optional,
    parse_plus,
)


def _token(type_: str, content: str = "", line: int = 1, column: int = 0) -> Token:
    """创建合成 Token。"""
    return Token(type=type_, content=content or type_, line=line, column=column)


def _fake_self(extra: dict | None = None) -> object:
    """创建最小 fake parser 对象，包含 _parse_* 函数所需的属性。"""
    base = {
        "_log_state": lambda *a, **kw: None,
        "_debug_token_info": lambda ctx: "",
        "_process_production_node": process_production_node,
        "_parse_token": parse_token,
        "_parse_seq": parse_seq,
        "_parse_choice": parse_choice,
        "_parse_repeat": parse_repeat,
        "_parse_optional": parse_optional,
        "_parse_plus": parse_plus,
        "_comment_anchors": [],
        "grammar_rules": {},
    }
    if extra:
        base.update(extra)
    return type("FakeParser", (), base)()


# ── 辅助：用合成 feat dict 直接调用 process_production_node ──

def _parse(feat: dict, tokens: list[Token], self_obj=None) -> Node | None:
    """用 process_production_node 解析一个 feat 节点。"""
    ctx = ParseContext(tokens)
    parser = self_obj or _fake_self()
    return process_production_node(parser, feat, ctx)


def _token_feat(token_type: str, optional: bool = False) -> dict:
    """创建 token 类型 feat 字典。"""
    return {"type": "token", "token_type": token_type, "optional": optional}


def _choice_feat(*alternatives: dict) -> dict:
    return {"type": "choice", "alternatives": list(alternatives)}


def _seq_feat(*items: dict) -> dict:
    return {"type": "seq", "items": list(items)}


def _repeat_feat(elem: dict) -> dict:
    return {"type": "repeat", "elem": elem}


def _plus_feat(elem: dict) -> dict:
    return {"type": "plus", "elem": elem}


def _optional_feat(elem: dict) -> dict:
    return {"type": "optional", "elem": elem}


# ═══════════════════════════════════════════════════════
# token — 精确匹配和可选匹配
# ═══════════════════════════════════════════════════════

class TestProdToken:
    def test_prod_token_exact_match(self):
        """精确匹配返回节点并推进指针。"""
        ctx = ParseContext([_token("keyword.foo")])
        parser = _fake_self()
        result = parse_token(parser, _token_feat("keyword.foo"), ctx)
        assert result is not None
        assert result.node_name == "keyword.foo"
        assert ctx.token_pointer == 1

    def test_prod_token_mismatch(self):
        """不匹配时返回 None，指针不动。"""
        ctx = ParseContext([_token("keyword.foo")])
        parser = _fake_self()
        result = parse_token(parser, _token_feat("keyword.bar"), ctx)
        assert result is None
        assert ctx.token_pointer == 0

    def test_prod_token_optional_present(self):
        """optional token 通过 _optional_feat 包裹。"""
        feat = _optional_feat(_token_feat("keyword.foo"))
        result = _parse(feat, [_token("keyword.foo")])
        assert result is not None
        assert result.node_name == "optional"
        assert len(result.sub_node) == 1

    def test_prod_token_optional_absent(self):
        """optional 不匹配时返回空的 optional node。"""
        feat = _optional_feat(_token_feat("keyword.foo"))
        result = _parse(feat, [_token("keyword.bar")])
        assert result is not None
        assert result.node_name == "optional"

    def test_prod_token_eof(self):
        """token 在 EOF 时返回 None。"""
        ctx = ParseContext([])
        parser = _fake_self()
        assert parse_token(parser, _token_feat("x"), ctx) is None


# ═══════════════════════════════════════════════════════
# choice — 分支选择
# ═══════════════════════════════════════════════════════

class TestProdChoice:
    def test_prod_choice_single_branch(self):
        """单分支匹配第一个分支。"""
        feat = _choice_feat(
            _token_feat("keyword.a"),
            _token_feat("keyword.b"),
        )
        result = _parse(feat, [_token("keyword.a")])
        assert result is not None
        assert result.node_name == "keyword.a"

    def test_prod_choice_fallback(self):
        """第一个分支不匹配，回退到第二个。"""
        feat = _choice_feat(
            _token_feat("keyword.a"),
            _token_feat("keyword.b"),
        )
        result = _parse(feat, [_token("keyword.b")])
        assert result is not None
        assert result.node_name == "keyword.b"

    def test_prod_choice_all_fail(self):
        """全部分支不匹配返回 None。"""
        feat = _choice_feat(
            _token_feat("keyword.a"),
            _token_feat("keyword.b"),
        )
        result = _parse(feat, [_token("keyword.c")])
        assert result is None

    def test_prod_choice_longest_match(self):
        """多个分支匹配时选最长的（多消费 token 的）。"""
        feat = _choice_feat(
            _seq_feat(_token_feat("a"), _token_feat("b")),  # 2 tokens
            _token_feat("a"),                                 # 1 token
        )
        result = _parse(feat, [_token("a"), _token("b")])
        assert result is not None
        assert result.node_name == "seq"

    def test_prod_choice_empty(self):
        """无分支的 choice 返回 None。"""
        result = _parse(_choice_feat(), [])
        assert result is None

    def test_prod_choice_multi_with_same_first(self):
        """多条分支首 token 相同，通过后续区分。"""
        feat = _choice_feat(
            _seq_feat(_token_feat("a"), _token_feat("b")),
            _seq_feat(_token_feat("a"), _token_feat("c")),
        )
        result = _parse(feat, [_token("a"), _token("c")])
        assert result is not None
        # 第二条分支匹配成功


# ═══════════════════════════════════════════════════════
# seq — 顺序组
# ═══════════════════════════════════════════════════════

class TestProdSeq:
    def test_prod_seq_all_success(self):
        """所有子项依次匹配成功。"""
        feat = _seq_feat(_token_feat("a"), _token_feat("b"), _token_feat("c"))
        result = _parse(feat, [_token("a"), _token("b"), _token("c")])
        assert result is not None
        assert result.node_name == "seq"

    def test_prod_seq_mid_fail(self):
        """中间子项失败 → 返回 None（外层 _try_production 负责回退）。"""
        feat = _seq_feat(_token_feat("a"), _token_feat("b"), _token_feat("c"))
        result = _parse(feat, [_token("a"), _token("x"), _token("c")])
        assert result is None

    def test_prod_seq_first_fail(self):
        """首子项失败 → 回退到起点。"""
        feat = _seq_feat(_token_feat("x"), _token_feat("y"))
        result = _parse(feat, [_token("a")])
        assert result is None

    def test_prod_seq_empty(self):
        """空 seq → 空节点。"""
        feat = _seq_feat()
        result = _parse(feat, [])
        assert result is not None


# ═══════════════════════════════════════════════════════
# repeat — 零或多次重复
# ═══════════════════════════════════════════════════════

class TestProdRepeat:
    def test_prod_repeat_zero(self):
        """不匹配时返回空列表。"""
        feat = _repeat_feat(_token_feat("a"))
        result = _parse(feat, [_token("b")])
        assert result is not None
        assert result.node_name == "repeat"
        assert len(result.sub_node) == 0

    def test_prod_repeat_once(self):
        """匹配一次。"""
        feat = _repeat_feat(_token_feat("a"))
        result = _parse(feat, [_token("a"), _token("b")])
        assert result is not None
        assert result.node_name == "repeat"
        assert len(result.sub_node) == 1

    def test_prod_repeat_many(self):
        """匹配多次。"""
        feat = _repeat_feat(_token_feat("a"))
        result = _parse(feat, [_token("a"), _token("a"), _token("a")])
        assert result is not None
        assert result.node_name == "repeat"
        assert len(result.sub_node) == 3

    def test_prod_repeat_stop_on_mismatch(self):
        """遇到不匹配立即停止。"""
        feat = _repeat_feat(_token_feat("a"))
        result = _parse(feat, [_token("a"), _token("a"), _token("x")])
        assert result is not None
        assert len(result.sub_node) == 2

    def test_prod_repeat_empty_input(self):
        """空输入返回空列表。"""
        result = _parse(_repeat_feat(_token_feat("a")), [])
        assert result is not None
        assert len(result.sub_node) == 0


# ═══════════════════════════════════════════════════════
# plus — 至少一次重复
# ═══════════════════════════════════════════════════════

class TestProdPlus:
    def test_prod_plus_once(self):
        """匹配一次。"""
        feat = _plus_feat(_token_feat("a"))
        result = _parse(feat, [_token("a")])
        assert result is not None

    def test_prod_plus_many(self):
        """匹配多次。"""
        feat = _plus_feat(_token_feat("a"))
        result = _parse(feat, [_token("a"), _token("a"), _token("a")])
        assert result is not None
        assert result.node_name == "plus"

    def test_prod_plus_zero_fails(self):
        """零次匹配 → None（plus 要求至少一次）。"""
        feat = _plus_feat(_token_feat("a"))
        result = _parse(feat, [_token("b")])
        assert result is None

    def test_prod_plus_empty_input_fails(self):
        """空输入 → None。"""
        result = _parse(_plus_feat(_token_feat("a")), [])
        assert result is None

    def test_prod_plus_stops_at_mismatch(self):
        """遇到不匹配停止。"""
        feat = _plus_feat(_token_feat("a"))
        result = _parse(feat, [_token("a"), _token("a"), _token("x")])
        assert result is not None


# ═══════════════════════════════════════════════════════
# optional — 零或一次
# ═══════════════════════════════════════════════════════

class TestProdOptional:
    def test_prod_optional_present(self):
        """optional 匹配时含子节点。"""
        result = _parse(_optional_feat(_token_feat("a")), [_token("a")])
        assert result is not None
        assert result.node_name == "optional"
        assert len(result.sub_node) == 1

    def test_prod_optional_absent(self):
        """optional 不匹配时返回空的 optional node。"""
        result = _parse(_optional_feat(_token_feat("a")), [_token("b")])
        assert result is not None
        assert result.node_name == "optional"

    def test_prod_optional_empty(self):
        """空输入返回空 optional。"""
        result = _parse(_optional_feat(_token_feat("a")), [])
        assert result is not None
        assert result.node_name == "optional"


# ═══════════════════════════════════════════════════════
# process_production_node 分发
# ═══════════════════════════════════════════════════════

class TestProdDispatch:
    def test_prod_dispatch_token(self):
        """分发到 _parse_token。"""
        result = _parse(_token_feat("x"), [_token("x")])
        assert result is not None
        assert result.node_name == "x"

    def test_prod_dispatch_seq(self):
        """分发到 _parse_seq。"""
        result = _parse(_seq_feat(_token_feat("a"), _token_feat("b")),
                        [_token("a"), _token("b")])
        assert result is not None
        assert result.node_name == "seq"

    def test_prod_dispatch_unknown_type(self):
        """未知 type 返回 None。"""
        result = _parse({"type": "unknown"}, [])
        assert result is None

    def test_prod_dispatch_missing_type(self):
        """无 type 字段返回 None。"""
        result = _parse({}, [])
        assert result is None
