"""片段变换 P0（显式记号）测试：identity/负例/死分支/幂等/真实文件。

Doc: tools/fragment_rewrite.py；docs/gaps/gap-fragment-mode.md
"""

from __future__ import annotations

from pathlib import Path

from tools.fragment_rewrite import rewrite_bytes

RULES = "grammar/verilog"
WRAP = (
    "// tpc:fragment id=rule1 begin\n"
    "always @(*) a <= b;\n"
    "// tpc:fragment end\n"
)


def _r(data: bytes):
    return rewrite_bytes(data, RULES)


def test_identity_four_byte_cases() -> None:
    """无记号时逐字节不变：LF / CRLF / BOM / 无尾换行。"""
    variants = [
        b"module m;\nendmodule\n",
        b"module m;\r\nendmodule\r\n",
        b"\xef\xbb\xbfmodule m;\nendmodule\n",
        b"module m;\nendmodule",
    ]
    for data in variants:
        result = _r(data)
        assert result.errors == []
        assert result.hits == 0
        assert result.output == data


def test_single_rule_hit_and_preserve_crlf_bom() -> None:
    data = b"\xef\xbb\xbf" + WRAP.replace("\n", "\r\n").encode("utf-8")
    result = _r(data)
    assert result.errors == []
    assert result.hits == 1
    assert b"always @* a <= b;" in result.output
    assert result.output.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in result.output


def test_fake_marker_in_string_is_ignored() -> None:
    data = (
        'module m; initial begin $display("// tpc:fragment id=fake begin"); end endmodule\n'
    ).encode("utf-8")
    result = _r(data)
    assert result.hits == 0 and result.errors == []
    assert result.output == data


def test_fake_marker_in_block_comment_is_ignored() -> None:
    data = (
        "module m;\n"
        "/* // tpc:fragment id=fake begin */\n"
        "always @(*) a <= b;\n"
        "endmodule\n"
    ).encode("utf-8")
    result = _r(data)
    # 没有真实 begin/end 记号 ⇒ 不进入任何区域，不做改写
    assert result.hits == 0 and result.errors == []
    assert result.output == data


def test_dead_branch_marker_is_water() -> None:
    data = (
        "`ifdef FOO\n"
        "// tpc:fragment id=dead begin\n"
        "always @(*) a <= b;\n"
        "// tpc:fragment end\n"
        "`endif\n"
        "// tpc:fragment id=live begin\n"
        "always @(*) c <= d;\n"
        "// tpc:fragment end\n"
    ).encode("utf-8")
    result = _r(data)
    assert result.errors == []
    assert result.hits == 1
    text = result.output.decode("utf-8")
    assert "always @(*) a <= b;" in text  # 死分支未被改写
    assert "always @* c <= d;" in text  # 活动分支被改写


def test_unclosed_begin_fails_closed() -> None:
    data = (
        "// tpc:fragment id=x begin\n"
        "always @(*) a <= b;\n"
    ).encode("utf-8")
    result = _r(data)
    assert result.hits == 0
    assert result.errors
    assert result.output == data


def test_nested_begin_fails_closed() -> None:
    data = (
        "// tpc:fragment id=a begin\n"
        "// tpc:fragment id=b begin\n"
        "always @(*) a <= b;\n"
        "// tpc:fragment end\n"
        "// tpc:fragment end\n"
    ).encode("utf-8")
    result = _r(data)
    assert result.errors
    assert result.output == data


def test_idempotent_double_run() -> None:
    first = _r(WRAP.encode("utf-8"))
    assert first.errors == [] and first.hits == 1
    second = _r(first.output)
    assert second.errors == [] and second.hits == 0
    assert second.output == first.output


def test_real_verilog_file_without_markers_is_byte_identical() -> None:
    sample = Path("tests/e2e/samples/check_accuracy/cases/AW001_blocking_in_timing/top.sv")
    data = sample.read_bytes()
    result = _r(data)
    assert result.errors == []
    assert result.output == data


def test_cli_dry_run_and_write(tmp_path) -> None:
    import subprocess
    import sys

    src = tmp_path / "frag.sv"
    src.write_text(WRAP, encoding="utf-8")
    dry = subprocess.run(
        [sys.executable, "main.py", "fragment", str(src)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert dry.returncode == 0
    assert "always @*" not in src.read_text(encoding="utf-8")
    write = subprocess.run(
        [sys.executable, "main.py", "fragment", "--write", str(src)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert write.returncode == 0
    assert "always @* a <= b;" in src.read_text(encoding="utf-8")
