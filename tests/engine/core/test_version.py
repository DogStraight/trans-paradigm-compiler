"""版本单一来源（TODO P2.2）：core.__version__ 与 pyproject.toml [project].version 一致，
`tpc --version` 输出该版本号（argparse version action，exit 0）。
"""

import io
import os
import sys
import tomllib
from contextlib import redirect_stdout

import pytest

from core import __version__


@pytest.fixture(scope="module")
def pyproject_version():
    # tests/engine/core/test_version.py → 4 级 dirname = 项目根
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    with open(os.path.join(root, "pyproject.toml"), "rb") as f:
        meta = tomllib.load(f)
    return meta["project"]["version"]


def test_core_version_matches_pyproject(pyproject_version):
    """core.__version__ 与 pyproject 的 [project].version 保持一致。"""
    assert __version__ == pyproject_version


def test_cli_version_flag():
    """`tpc --version` 打印版本号并以 0 退出。"""
    import main

    old_argv = sys.argv
    sys.argv = ["tpc", "--version"]
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            with pytest.raises(SystemExit) as e:
                main.main()
        assert e.value.code == 0
        assert __version__ in buf.getvalue()
    finally:
        sys.argv = old_argv
