"""tpc lint CLI 入口测试（main.py 路径）。

linter/cli.py 已删除（与 main.py _cmd_lint 功能重复的劣化实现——硬编码
相对路径、不支持 wheel 安装后运行）；CLI 唯一入口是 `tpc lint`（main.py）。
本测试用 subprocess 跑真实进程，覆盖 CLI 级行为（文件/stdin/--json/
退出码）。

Doc: api.md（CLI 入口）
"""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.usefixtures("config_loaded")

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_MAIN = os.path.join(_ROOT, "main.py")


def _run_lint(*args, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=_ROOT)
    return subprocess.run(
        [sys.executable, _MAIN, "lint", *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
        cwd=_ROOT,
        encoding="utf-8",
    )


class TestLintCli:
    def test_file_input_clean(self, tmp_path):
        """文件输入：干净代码 → 退出 0，无输出。"""
        f = tmp_path / "m.v"
        f.write_text("module m;\n    reg a;\nendmodule\n", encoding="utf-8")
        r = _run_lint(str(f))
        assert r.returncode == 0, r.stderr

    def test_file_input_error(self, tmp_path):
        """文件输入：有错误 → 退出 1，输出诊断。"""
        f = tmp_path / "bad.v"
        f.write_text("module m;\n    reg a,;\nendmodule\n", encoding="utf-8")
        r = _run_lint(str(f))
        assert r.returncode == 1
        assert "Ln" in r.stdout or "error" in r.stdout.lower()

    def test_stdin_input(self):
        """stdin 输入：管道喂源码 → 正常扫描。"""
        r = _run_lint(stdin="module m;\n    wire w;\nendmodule\n")
        assert r.returncode == 0, r.stderr

    def test_json_output(self, tmp_path):
        """--json：LSP 兼容 JSON 输出。"""
        f = tmp_path / "bad.v"
        f.write_text("module m;\n    reg a,;\nendmodule\n", encoding="utf-8")
        r = _run_lint(str(f), "--json")
        assert r.returncode == 1
        import json
        data = json.loads(r.stdout)  # 应为 JSON 数组
        assert isinstance(data, list)

    def test_no_input(self):
        """无输入 → 退出 1 + "No input"。"""
        r = _run_lint(stdin="")
        assert r.returncode == 1
        assert "No input" in r.stderr
