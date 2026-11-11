"""动态测试入口的判据（审查侧 2026-11-11 定，5 条硬判据）。

被测对象：`tools/affected_tests.py` + `tests/affected_map.toml`。
本测试只做**选择逻辑/映射表健康/缓存守卫**——不真跑全量（选择器不决定 CI/发布）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import affected_tests as tool  # noqa: E402  # pyright: ignore[reportMissingImports]


def _map() -> dict:
    return tool._load_map()


class TestMapHealth:
    def test_map_paths_exist_and_entries_nonempty(self) -> None:
        """判据 5：表里每个路径存在、条目非空（--audit-map 绿）。"""
        assert tool.audit_map(_map()) == []
        assert tool.main(["--audit-map"]) == 0

    def test_audit_map_flags_missing_path(self) -> None:
        """映射表防腐反向演练：删一个路径/清空 runs ⇒ 必须报违规。"""
        broken = {
            "full_prefixes": ["no_such_dir/"],
            "rule": [{"name": "x", "prefixes": ["parser/"], "runs": []}],
            "suffix_rule": [],
        }
        errors = tool.audit_map(broken)
        assert any("full_prefixes" in e for e in errors)
        assert any("runs 为空" in e for e in errors)


class TestSelection:
    def test_unknown_path_forces_full(self) -> None:
        """判据 1：未映射路径（lexer/）⇒ 全量。"""
        selection = tool.select(["lexer/main_lexer.py"], _map())
        assert selection.mode == "full"
        assert selection.commands == (("-m", "pytest", "tests", "-q"),)
        assert "未映射" in selection.reasons[0]

    def test_policy_layer_forces_full(self) -> None:
        for path in ("core/define.py", "policy/session-wire.md", "tools/ci_rehearsal.py"):
            selection = tool.select([path], _map())
            assert selection.mode == "full", path

    def test_parser_maps_to_parser_suite(self) -> None:
        selection = tool.select(["parser/follow.py"], _map())
        assert selection.mode == "selected"
        assert ("-m", "pytest", "tests/engine/parser", "-q") in selection.commands

    def test_linter_maps_to_linter_suite_and_accuracy(self) -> None:
        selection = tool.select(["linter/lookahead.py"], _map())
        assert selection.mode == "selected"
        assert ("-m", "pytest", "tests/engine/linter", "-q") in selection.commands
        assert ("tests/e2e/eval_lint_accuracy.py",) in selection.commands

    def test_language_pack_maps_to_language_suite_plus_smoke(self) -> None:
        selection = tool.select(["grammar/c/00_expressions.toml"], _map())
        assert selection.mode == "selected"
        assert ("-m", "pytest", "tests/languages/c", "-q") in selection.commands
        assert ("-m", "pytest", "-m", "smoke", "-q") in selection.commands

    def test_unknown_language_pack_forces_full(self) -> None:
        selection = tool.select(["grammar/nope/x.toml"], _map())
        assert selection.mode == "full"

    def test_docs_map_to_doc_gates(self) -> None:
        selection = tool.select(["docs/README.md"], _map())
        assert selection.mode == "selected"
        flat = {tuple(run) for run in selection.commands}
        assert ("policy/check_doc_refs.py", "--strict-input") in flat
        assert any(
            "tests/policy/test_doc_sync.py" in part
            for run in selection.commands
            for part in run
        )

    def test_test_file_maps_to_itself(self) -> None:
        selection = tool.select(["tests/engine/parser/test_follow.py"], _map())
        assert selection.mode == "selected"
        assert ("-m", "pytest", "tests/engine/parser/test_follow.py", "-q") in selection.commands

    def test_test_infrastructure_forces_full(self) -> None:
        selection = tool.select(["tests/helpers.py"], _map())
        assert selection.mode == "full"

    def test_empty_change_forces_full(self) -> None:
        """异常路径保守回全量（不许"没改动=没事"）。"""
        assert tool.select([], _map()).mode == "full"


class TestCache:
    def test_cached_exit_reuses_only_selected_mode(self) -> None:
        """判据 2：缓存按模式区分；全量档永不缓存。"""
        state = {"fingerprint": "abc", "exit": 3}
        assert tool.cached_exit(state, "abc", "selected") == 3
        assert tool.cached_exit(state, "abc", "full") is None
        assert tool.cached_exit(state, "other", "selected") is None
        assert tool.cached_exit({}, "abc", "selected") is None

    def test_fingerprint_covers_mode_and_paths(self) -> None:
        """指纹对"改了什么/模式"敏感（内容指纹由 fingerprint() 组合）。"""
        fp_selected = tool.fingerprint(["parser/follow.py"], "selected")
        fp_other = tool.fingerprint(["parser/follow.py", "linter/first_set.py"], "selected")
        fp_full = tool.fingerprint(["parser/follow.py"], "full")
        assert len(fp_selected) == 64
        assert fp_selected != fp_other
        assert fp_selected != fp_full


class TestSkippedAccounting:
    def test_skipped_tests_entries_must_have_reason(self) -> None:
        """判据 4：跳过记账——tests/ 条目没有理由即红。"""
        tool.assert_skipped_reasons((("tests/engine/parser", "未变更"),))
        with pytest.raises(RuntimeError):
            tool.assert_skipped_reasons((("tests/engine/parser", ""),))

    def test_dry_run_writes_select_log(self, tmp_path: Path) -> None:
        """判据 4：每次打印 selected/skipped 并落 select.log。"""
        log_path = tmp_path / "select.log"
        code = tool.main([
            "--simulate-changed", "parser/follow.py", "--dry-run",
            "--state", str(tmp_path / "state.json"), "--log", str(log_path),
        ])
        assert code == 0
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert lines and json.loads(lines[-1])["dry_run"] is True
        assert "selected=" in lines[-1] or json.loads(lines[-1])["mode"] == "selected"

    def test_cached_reuse_returns_previous_exit(self, tmp_path: Path) -> None:
        """无变化复用：写入状态后同指纹再跑 → 不执行命令、原样返回上次 exit。"""
        state = tmp_path / "state.json"
        log_path = tmp_path / "select.log"
        assert tool.main([
            "--simulate-changed", "parser/follow.py", "--dry-run",
            "--state", str(state), "--log", str(log_path),
        ]) == 0
        # dry-run 不写缓存；手工写入"当前指纹 + exit 7"后验证复用
        selection = tool.select(["parser/follow.py"], _map())
        fp = tool.fingerprint(list(selection.changed), selection.mode)
        state.write_text(json.dumps({"fingerprint": fp, "exit": 7, "ts": "t"}), encoding="utf-8")
        assert tool.main([
            "--simulate-changed", "parser/follow.py",
            "--state", str(state), "--log", str(log_path),
        ]) == 7
