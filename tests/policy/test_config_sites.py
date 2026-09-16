"""tools/config_sites.py 自测：同步点位枚举的整键匹配/子串安全 + 真实仓库回归。

单元用例在 tmp_path 上构造最小语言包（含"陷阱键"：`break_distance` /
`first_soft` / `no_soft`——都以 `break`/`soft` 为子串），验证：
  - `list --key break` 只命中**整键**（不命中 `break_distance`）
  - `rename` 只改键 token（同行其余键/值/注释/`break_distance` 全不动）；
    `--value` 过滤生效；默认 dry-run 不写盘
  - `check` 词表外的键 → FAIL（配置漂移哨兵）
回归用例跑真实仓库：`check` 必须 PASS；`break` 点位清单可枚举。

Doc: policy/engine_config_sync.md
"""

import importlib.util
import sys
from pathlib import Path

_TOOL_PATH = Path(__file__).resolve().parent.parent.parent / "tools" / "config_sites.py"

_PACK_TOML = "[pipeline]\nunits = []\n"

_SAMPLE = """# 对齐段
[Rule.renderer.head]
line = [
    { break = true, indent = 1 },
    { break = false },
    { soft = true },
]
break_distance = 3
first_soft = true
no_soft = true
"""


def _load_tool():
    spec = importlib.util.spec_from_file_location("config_sites", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tool = _load_tool()


def _make_pack(tmp_path: Path, body: str = _SAMPLE) -> Path:
    """最小语言包：tpc.toml（包根标识）+ a.toml（渲染段配置）。"""
    pack = tmp_path / "grammar" / "v"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "tpc.toml").write_text(_PACK_TOML, encoding="utf-8")
    (pack / "a.toml").write_text(body, encoding="utf-8")
    return pack


def _sites(tmp_path: Path, key: str | None = None) -> list:
    """按最小包枚举点位（--root tmp_path，不碰真实仓库）。"""
    pack = _make_pack(tmp_path)
    sites = tool._collect(str(tmp_path), [str(pack)], renderer_only=True)
    return [s for s in sites if s["key"] == key] if key else sites


def test_key_match_is_exact_not_substring(tmp_path):
    """整键相等：`break` 不命中 `break_distance`；`soft` 不命中 `first_soft`。"""
    keys = {s["key"] for s in _sites(tmp_path)}
    assert {"break", "soft", "break_distance", "first_soft", "no_soft"} <= keys
    breaks = _sites(tmp_path, "break")
    assert len(breaks) == 2, breaks                      # 两个 { break = ... }
    assert {s["value"] for s in breaks} == {"true", "false"}
    assert len(_sites(tmp_path, "soft")) == 1            # { soft = true }


def test_sites_carry_position_and_section(tmp_path):
    """点位带 file:line / 段路径 / 原值（可核对、可逐项替换）。"""
    site = _sites(tmp_path, "break")[0]
    assert site["file"].endswith("a.toml")
    assert site["section"] == "Rule.renderer.head"
    assert site["line"] > 0 and site["raw"].strip()


def test_rename_only_touches_key_token(tmp_path):
    """rename 只换键 token：同行其余键/值/`break_distance` 全不动。"""
    pack = _make_pack(tmp_path)
    rc = tool.main(
        ["rename", "--root", str(tmp_path), "--pack", str(pack), "--renderer-only",
         "--from", "break", "--to", "hard_break", "--value", "true", "--apply"]
    )
    assert rc == 0
    text = (pack / "a.toml").read_text(encoding="utf-8")
    assert "{ hard_break = true, indent = 1 }" in text   # 仅此一处被改
    assert "{ break = false }" in text                   # 值不匹配 → 不动
    assert "break_distance = 3" in text                  # 子串不误伤
    assert text.count("hard_break") == 1


def test_rename_dry_run_does_not_write(tmp_path):
    pack = _make_pack(tmp_path)
    before = (pack / "a.toml").read_text(encoding="utf-8")
    tool.main(
        ["rename", "--root", str(tmp_path), "--pack", str(pack), "--renderer-only",
         "--from", "break", "--to", "hard_break"]
    )
    assert (pack / "a.toml").read_text(encoding="utf-8") == before


def test_check_flags_key_outside_vocabulary(tmp_path, capsys):
    """词表外的键 → FAIL（配置漂移哨兵）。"""
    pack = _make_pack(tmp_path, "[Rule.renderer.head]\nline = [ { brek = true } ]\n")
    assert tool.main(["check", "--root", str(tmp_path), "--pack", str(pack)]) == 1
    assert "brek" in capsys.readouterr().out


def test_check_skips_structural_keys(tmp_path):
    """`override` 下的规则名与容器键是结构键（不误报为漂移）。"""
    body = (
        "[Rule.renderer.head]\n"
        "override = { BeginEnd = { tail_break = 2 } }\n"
        "body = { source = \"items\" }\n"
    )
    pack = _make_pack(tmp_path, body)
    assert tool.main(["check", "--root", str(tmp_path), "--pack", str(pack)]) == 0


def test_check_passes_on_sample_pack(tmp_path):
    pack = _make_pack(tmp_path)
    assert tool.main(["check", "--root", str(tmp_path), "--pack", str(pack)]) == 0


def test_check_reports_multi_dispatch_shadowing(tmp_path, capsys):
    """同一 dict 多个原语键：只有注册顺序最前的生效（`ref` 遮蔽 `group`）。"""
    body = (
        "[Rule.renderer.head]\n"
        "line = [ { opt = { group = [ { break = true } ], ref = \"ports\" } } ]\n"
    )
    pack = _make_pack(tmp_path, body)
    assert tool.main(["check", "--root", str(tmp_path), "--pack", str(pack)]) == 0
    out = capsys.readouterr().out
    assert "生效=ref" in out and "group" in out
    assert "break@" in out          # 被遮蔽子树内的 break 一并列为失效


def test_line_array_elements_not_flagged_as_shadowed(tmp_path, capsys):
    """`line` 数组元素由 eval_line 内联消费（soft/break 与 indent 共存合法）。"""
    body = (
        "[Rule.renderer.head]\n"
        "line = [ { break = true, indent = 1 }, { soft = true } ]\n"
    )
    pack = _make_pack(tmp_path, body)
    assert tool.main(["check", "--root", str(tmp_path), "--pack", str(pack)]) == 0
    assert "静默失效）0 处" in capsys.readouterr().out


def test_real_repo_renderer_config_has_no_drift():
    """真实仓库回归：渲染段无引擎词汇表以外的键（漂移哨兵基线）。"""
    assert tool.main(["check"]) == 0


def test_real_repo_break_sites_inventory_nonempty(capsys):
    """真实仓库回归：`break` 点位清单非空且带 file:line（改造面可枚举）。"""
    assert tool.main(["list", "--key", "break", "--renderer-only"]) == 0
    out = capsys.readouterr().out
    assert "grammar/verilog" in out and ".toml:" in out
