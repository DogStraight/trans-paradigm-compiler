"""宏展开锚名协议（core/token_protocol）——唯一性 / 可复现性 / 还原守卫。

锚是引擎占位：用户代码写不出（保留前缀 __tpc_），文件间不撞（盐来自源文本
摘要），文件内互不相同（序号递增），跨进程可复现（sha256，非内置 hash()）。
Doc: core/token_protocol.py（锚名协议） / docs/decisions/0017
"""

import hashlib

import pytest

from core.token_protocol import (
    ANCHOR_MARK,
    RESERVED_PREFIX,
    anchor_name,
    anchor_salt,
)
from preprocessor._bridge import restore_anchors


class TestAnchorSalt:
    """盐 = 源文本摘要：可复现、随源变化、不依赖进程随机化。"""

    def test_salt_is_source_digest(self) -> None:
        """盐等于 sha256(源文本) 前 8 位——不是内置 hash()。

        内置 hash() 受 PYTHONHASHSEED 随机化影响：跨进程不可复现，同一输入的
        两次运行会得到不同锚名（还原/对拍不可复现）。等值断言把这一约束钉死。
        """
        src = "module m;\n  wire a;\nendmodule\n"
        expected = hashlib.sha256(src.encode("utf-8")).hexdigest()[:8]
        assert anchor_salt(src) == expected

    def test_salt_deterministic(self) -> None:
        assert anchor_salt("abc") == anchor_salt("abc")

    def test_salt_differs_per_source(self) -> None:
        """不同源文本 → 不同盐（文件间不撞锚）。"""
        assert anchor_salt("module a; endmodule") != anchor_salt("module b; endmodule")

    def test_salt_shape(self) -> None:
        salt = anchor_salt("x")
        assert len(salt) == 8
        assert all(ch in "0123456789abcdef" for ch in salt)


class TestAnchorName:
    """锚名 = 保留前缀 + marker + 盐 + 序号。"""

    def test_name_shape(self) -> None:
        name = anchor_name(3, "deadbeef")
        assert name == f"{RESERVED_PREFIX}{ANCHOR_MARK}_deadbeef_3"

    def test_names_unique_within_file(self) -> None:
        salt = anchor_salt("src")
        names = [anchor_name(i, salt) for i in range(1, 6)]
        assert len(set(names)) == 5

    def test_names_differ_across_files(self) -> None:
        """同序号、不同文件 → 不同锚名（用户文本偶然出现在别的文件里不撞）。"""
        assert anchor_name(1, anchor_salt("a")) != anchor_name(1, anchor_salt("b"))

    def test_name_is_user_unwritable_identifier(self) -> None:
        """锚名带用户不可能主动使用的保留前缀（用户若用须报保留名占用）。"""
        assert anchor_name(1, "deadbeef").startswith(RESERVED_PREFIX)

    def test_anchor_name_is_plain_identifier(self) -> None:
        """锚是**普通标识符**形态：语言包不认识宏，解析照常接受。

        锚不给语言包留语法槽位（宏位置本质是文本任意的，逐槽位声明补不齐且
        某些槽位会静默错渲染，见 ADR-0017 决策 3）。
        """
        name = anchor_name(1, "deadbeef")
        assert name.isidentifier(), name


class TestTokenRestoreGuard:
    """token 锚还原的唯一性守卫：仅恰好命中一次才回插。"""

    def _entry(self, marker: str) -> list[dict]:
        return [
            {
                "marker": marker,
                "source_text": "`NAME",
                "mode": "token",
                "kind": "macro",
            }
        ]

    def _marker(self, seq: int = 1) -> str:
        return anchor_name(seq, "deadbeef")

    def test_restore_single_hit(self) -> None:
        marker = self._marker()
        rendered = f"wire [7:0] a;\n  assign a = {marker};\n"
        out = restore_anchors(rendered, self._entry(marker))
        assert out == "wire [7:0] a;\n  assign a = `NAME;\n"

    def test_restore_skips_when_ambiguous(self) -> None:
        """锚文本出现两次（用户文本恰含锚名）→ 保留占位，不做静默错还原。"""
        marker = self._marker()
        rendered = f"a = {marker};\nb = {marker};\n"
        out = restore_anchors(rendered, self._entry(marker))
        assert out == rendered

    def test_restore_skips_when_absent(self) -> None:
        """锚文本 0 次（渲染路径已用原文直出）→ 不动作，不误改文本。"""
        marker = self._marker()
        rendered = "a = `NAME;\n"
        assert restore_anchors(rendered, self._entry(marker)) == rendered

    def test_prefix_marker_not_matched(self) -> None:
        """锚名是更长锚名的前缀 → 不误匹配（序号 1 不吃序号 10）。"""
        short = self._marker(1)
        long = self._marker(10)
        rendered = f"a = {long};\n"
        assert restore_anchors(rendered, self._entry(short)) == rendered


@pytest.mark.parametrize("seq", [1, 99, 12345])
def test_anchor_lexes_as_identifier(config_loaded, seq: int) -> None:
    """锚在 lexer 中归为 `id`（与普通标识符同形，语言包不做宏特化）。"""
    from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR
    from lexer import Lexer

    text = anchor_name(seq, anchor_salt("src"))
    tokens = Lexer(rules_dir=DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS).tokenize(
        text
    )
    assert tokens[0].type == "id", tokens[0].type
    assert tokens[0].content == text
