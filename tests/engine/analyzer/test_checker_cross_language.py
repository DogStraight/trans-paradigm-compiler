"""跨语言同进程：C → verilog → C 的第二轮 C 诊断不得丢失。

`SharedComponents` 缓存命中只复用规则/词法对象；`setup_grammar` 会清空全局
`_loaded_components`，必须把组件注册表重建为当前语言（postpass/CSC/LAB/MAC
依赖它），否则第二轮 C 检查静默丢诊断（库入口，单语言 CLI 不复现）。
"""

from __future__ import annotations

from analyzer.checker import ProjectChecker


def _codes(path: str) -> list[str]:
    chk = ProjectChecker(rules_dir="grammar/c", ext_dirs=None, include_dirs=[])
    rep = chk.check(path)
    f = rep["files"][0]
    return [
        str(d.get("code"))
        for d in (f.get("syntax") or []) + (f.get("semantic") or [])
    ]


def test_c_verilog_c_second_round_keeps_postpass(tmp_path) -> None:
    c_path = tmp_path / "lab.c"
    c_path.write_text("void f(void){ lab: ; lab: ; }\n", encoding="utf-8")
    v_path = tmp_path / "m.v"
    v_path.write_text("module m; endmodule\n", encoding="utf-8")

    first = _codes(str(c_path))
    assert "LAB001" in first

    verilog = ProjectChecker(rules_dir="grammar/verilog", ext_dirs=None, include_dirs=[])
    verilog.check(str(v_path))

    second = _codes(str(c_path))
    assert second == first, f"C→V→C 诊断丢失：{first} vs {second}"
