"""report_html 渲染测试 — check report dict → HTML 的关键输出点。

验证：severity 徽标 / 0-based→显示位置 +1 / message HTML escape /
related 溯源链 / 全干净文件跳过 / 空报告 "No issues found"。
"""

from analyzer.report_html import render_html_report


def _report(semantic, syntax=None, parse_ok=True, path="rtl/top.v"):
    return {
        "files": [
            {
                "path": path,
                "parse_ok": parse_ok,
                "parse_error": None,
                "syntax": syntax or [],
                "semantic": semantic,
            }
        ],
        "exit_code": 1 if semantic or syntax else 0,
    }


def test_empty_report_no_issues():
    out = render_html_report(_report(semantic=[]))
    assert "<title>tpc check report</title>" in out
    assert "No issues found." in out
    assert "0 error" in out


def test_clean_file_skipped():
    # parse_ok 且无诊断 → 不产文件卡片，走 No issues
    out = render_html_report(_report(semantic=[]))
    assert "top.v" not in out


def test_semantic_diag_row():
    report = _report(
        semantic=[
            {
                "stage": "semantic",
                "file": "rtl/top.v",
                "severity": 1,
                "code": "W104",
                "message": "missing port",
                "level": "error",
                "range": {
                    "start": {"line": 1, "character": 2},
                    "end": {"line": 1, "character": 3},
                },
                "related": [
                    {"message": "defined here", "file": "rtl/def.v", "line": 5, "column": 1}
                ],
            }
        ]
    )
    out = render_html_report(report)
    assert "sev-error" in out  # severity 1 → error 徽标
    assert "W104" in out
    assert "top.v:2:3" in out  # 0-based (line 1, char 2) → 显示 2:3
    assert "missing port" in out
    assert "defined here" in out
    assert "def.v:5:1" in out  # related 溯源位置
    assert "1 error" in out


def test_warning_and_info_levels():
    report = _report(
        semantic=[
            {"stage": "semantic", "file": "rtl/top.v", "severity": 2,
             "code": "UN001", "message": "unused", "level": "warning",
             "range": None},
            {"stage": "semantic", "file": "rtl/top.v", "severity": 3,
             "code": "AW001", "message": "style", "level": "info", "range": None},
        ]
    )
    out = render_html_report(report)
    assert "sev-warning" in out and "sev-info" in out
    assert "1 warning" in out and "1 info" in out


def test_message_escaped():
    # 诊断 message 里的 HTML 字符必须转义，不注入
    report = _report(
        semantic=[
            {"stage": "semantic", "file": "rtl/top.v", "severity": 1,
             "code": "X", "message": "<script>alert(1)</script> & 'q'",
             "level": "error", "range": None},
        ]
    )
    out = render_html_report(report)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_parse_error_file_included():
    # 解析失败文件：即使无诊断也出卡片 + parse error 徽标 + parse_error 信息
    report = {
        "files": [
            {
                "path": "rtl/broken.v",
                "parse_ok": False,
                "parse_error": "syntax error at line 3",
                "syntax": [],
                "semantic": [],
            }
        ],
        "exit_code": 1,
    }
    out = render_html_report(report)
    assert "sev-error" in out  # parse error 徽标
    assert "broken.v" in out
    assert "syntax error at line 3" in out
