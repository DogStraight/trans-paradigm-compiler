"""tests/core/test_errors.py — 统一异常层级测试。

覆盖（异常层级统一）：
    - 所有自定义异常继承 TransParadigmError（可按类型统一捕获）
    - core.define re-export ParseError（`from core.define import ParseError` 兼容）
    - ParseError 保留字段（token/rule/path/candidates/context_info）与消息格式

配置加载抛 ConfigError 的路径由 test_config_loading.py 覆盖。
"""

import pytest

from core.errors import (
    TransParadigmError,
    ConfigError,
    GrammarError,
    LexError,
    ParseError,
    TransformError,
    LintInternalError,
)
from core import define
from core.define import ParseError as DefineParseError


class TestHierarchy:
    """所有自定义异常都继承 TransParadigmError。"""

    @pytest.mark.parametrize(
        "exc",
        [
            ConfigError,
            GrammarError,
            LexError,
            ParseError,
            TransformError,
            LintInternalError,
        ],
    )
    def test_all_subclass_trans_paradigm_error(self, exc):
        assert issubclass(exc, TransParadigmError)
        assert issubclass(exc, Exception)

    def test_trans_paradigm_error_unified_catch(self):
        for exc in (ConfigError("x"), ParseError("x"), GrammarError("x")):
            try:
                raise exc
            except TransParadigmError:
                pass  # 统一按类型捕获生效
            else:
                raise AssertionError(f"{exc} 未被 TransParadigmError 捕获")

    def test_define_reexports_parse_error(self):
        # core.define re-export，保持 `from core.define import ParseError` 兼容
        assert DefineParseError is ParseError

    def test_plain_exception_not_trans_paradigm(self):
        assert not issubclass(ValueError, TransParadigmError)


class TestParseError:
    """ParseError 保留字段与消息格式。"""

    def test_fields_and_message(self):
        tok = define.Token("foo", "id", 3, 0)
        err = ParseError("boom", token=tok, rule="AlwaysStmt", path="Root/AlwaysStmt")
        assert err.token is tok
        assert err.rule == "AlwaysStmt"
        assert err.path == "Root/AlwaysStmt"
        assert "boom" in str(err)
        assert "token: 'foo'" in str(err)
        assert "AlwaysStmt" in str(err)
        assert "Ln 3" in str(err)

    def test_candidates_message(self):
        err = ParseError("x", candidates=["A", "B"])
        assert "candidates" in str(err)
        assert "A" in str(err)

    def test_context_info_message(self):
        err = ParseError("x", context_info="depth 5")
        assert "ctx: depth 5" in str(err)

    def test_empty_message(self):
        assert str(ParseError()) == ""


class TestConfigErrorIsFailFast:
    """ConfigError 触发路径（复用 config_registry 契约，非隔离 fixture）。"""

    def test_config_error_message_shape(self):
        e = ConfigError("[ConfigRegistry] 以下配置加载失败：\n  [t.x] 损坏")
        assert "配置加载失败" in str(e)
