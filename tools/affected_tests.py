"""affected_tests.py — 动态测试入口：按改动选测试子集（**日常快反馈**档）。

定位（审查侧 2026-11-11 定，规格 `.scratch/audit/dynamic-test-entry-review.md`）：
- 只服务"改完立刻知道该跑哪几个测试"，**不决定** CI/发布跑什么；
- CI 与 `ci_rehearsal` 永远全量；CI 只额外检查本工具的映射表健康（`--audit-map`）；
- 未知即全量：未映射路径、策略层（core/analyzer/pipeline/policy/tools/tests/policy）
  一律回退全量，绝不静默跳过。

行为：
  1. 变化来源 = `git diff --name-only HEAD` + 未跟踪文件（或 `--since <ref>`）；
  2. 按 `tests/affected_map.toml` 映射到 pytest/脚本 argv；
  3. 无变化（HEAD + 工作区脏指纹 + pytest 版本一致）⇒ 直接复用上次结果
     （exit code 原样返回；**全量档永不缓存**）；
  4. 每次打印并记账 `selected=N skipped=M reasons=[...]` 到 `.scratch/gate/select.log`。

用法：
    python tools/affected_tests.py                 # 日常：按改动选测（无变化复用）
    python tools/affected_tests.py --dry-run       # 只看选择，不执行
    python tools/affected_tests.py --full          # 强制全量（不缓存）
    python tools/affected_tests.py --audit-map     # 映射表健康（CI 用）
    python tools/affected_tests.py --simulate-changed parser/x.py --dry-run
Doc: tools/README.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = str(ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from core.console import ensure_utf8_stdio  # noqa: E402 — 路径引导之后才可 import

ensure_utf8_stdio()

MAP_PATH = ROOT / "tests" / "affected_map.toml"
DEFAULT_STATE = ROOT / ".scratch" / "gate" / "affected_state.json"
DEFAULT_LOG = ROOT / ".scratch" / "gate" / "select.log"
DEFAULT_TIMEOUT = 900


@dataclass(frozen=True)
class Selection:
    """一次选测结果；`mode=="full"` 表示回退全量。"""

    mode: str
    changed: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    skipped: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.stdout


def changed_paths(since: str | None) -> list[str]:
    """改动路径：`--since <ref>` 或（默认）HEAD 对比 + 未跟踪文件。"""
    if since:
        raw = _git(["diff", "--name-only", since])
    else:
        raw = _git(["diff", "--name-only", "HEAD"])
        raw += "\n" + _git(["ls-files", "--others", "--exclude-standard"])
    return sorted({_norm(p) for p in raw.splitlines() if p.strip()})


def _load_map(map_path: Path = MAP_PATH) -> dict:
    return tomllib.loads(map_path.read_text(encoding="utf-8"))


def _map_rules(map_data: dict) -> list[dict]:
    return list(map_data.get("rule") or [])


def _all_run_labels(map_data: dict) -> list[str]:
    """映射表里全部目标标签（用于 skipped 记账，不做占位展开）。"""
    labels: list[str] = []
    for rule in _map_rules(map_data):
        name = str(rule.get("name") or "rule")
        for run in rule.get("runs") or []:
            labels.append(f"{name}:{' '.join(run)}")
    for suffix_rule in map_data.get("suffix_rule") or []:
        name = str(suffix_rule.get("name") or "suffix")
        for run in suffix_rule.get("runs") or []:
            labels.append(f"{name}:{' '.join(run)}")
    return labels


def _is_full_path(path: str, map_data: dict) -> bool:
    for prefix in map_data.get("full_prefixes") or []:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def _full_selection(changed: list[str], reason: str) -> Selection:
    return Selection(
        mode="full",
        changed=tuple(changed),
        commands=(("-m", "pytest", "tests", "-q"),),
        skipped=(),
        reasons=(reason,),
    )


def _match_rule(path: str, map_data: dict) -> dict | None:
    """最长前缀匹配（不含 docs 后缀规则；grammar/tests-self 由调用方先处理）。"""
    best: dict | None = None
    best_len = -1
    for rule in _map_rules(map_data):
        if rule.get("self_tests"):
            continue
        for prefix in rule.get("prefixes") or []:
            if path.startswith(prefix) and len(prefix) > best_len:
                best, best_len = rule, len(prefix)
    return best


def _add_runs(runs: list[tuple[str, ...]], extra: list) -> None:
    for run in extra or []:
        argv = tuple(str(part) for part in run)
        if argv and argv not in runs:
            runs.append(argv)


def _doc_runs(map_data: dict) -> list:
    for suffix_rule in map_data.get("suffix_rule") or []:
        suffixes = suffix_rule.get("suffixes") or []
        if any(str(s).endswith(".md") for s in suffixes):
            return list(suffix_rule.get("runs") or [])
    return []


def _lang_runs(rule: dict, lang: str) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for run in rule.get("runs") or []:
        out.append(tuple(str(part).replace("{lang}", lang) for part in run))
    return out


def _language_runs(path: str, map_data: dict) -> tuple[list[tuple[str, ...]], str] | None:
    """`grammar/<lang>/...` → (语言包测试 + smoke, 理由)；未知语言包 → None。"""
    parts = path.split("/")
    lang = parts[1] if len(parts) > 1 else ""
    if not lang or not (ROOT / "tests" / "languages" / lang).is_dir():
        return None
    rule = next((r for r in _map_rules(map_data) if r.get("name") == "grammar"), None)
    if rule is None:
        return None
    return _lang_runs(rule, lang), f"语言包 {lang}：{path} ⇒ tests/languages/{lang} + smoke"


def _tests_self_runs(path: str) -> tuple[list[tuple[str, ...]], str] | None:
    """`tests/**/test_*.py` → 只跑该文件；测试基础设施 → None（回全量）。"""
    if path.endswith(".py") and Path(path).name.startswith("test_"):
        return [("-m", "pytest", path, "-q")], f"测试自身：{path} ⇒ 只跑该文件"
    return None


def _runs_for_path(path: str, map_data: dict) -> tuple[list[tuple[str, ...]], str] | None:
    """单个改动路径 → (runs, 理由)；None = 必须回退全量。"""
    if path.endswith(".md"):
        return [tuple(str(part) for part in run) for run in _doc_runs(map_data)], \
            f"文档：{path} ⇒ 文档门禁"
    if path.startswith("grammar/"):
        return _language_runs(path, map_data)
    if path.startswith("tests/"):
        return _tests_self_runs(path)
    rule = _match_rule(path, map_data)
    if rule is None:
        return None
    runs = [tuple(str(part) for part in run) for run in rule.get("runs") or []]
    return runs, f"{rule.get('name')}：{path}"


def _first_full_prefix(paths: list[str], map_data: dict) -> str | None:
    for path in paths:
        if _is_full_path(path, map_data):
            return path
    return None


def _collect_runs(
    paths: list[str], map_data: dict
) -> tuple[list[tuple[str, ...]], list[str]] | str:
    """收集各路径的 runs；返回失败路径字符串 = 必须回退全量。"""
    runs: list[tuple[str, ...]] = []
    reasons: list[str] = []
    for path in paths:
        item = _runs_for_path(path, map_data)
        if item is None:
            return path
        path_runs, reason = item
        _add_runs(runs, path_runs)
        reasons.append(reason)
    return runs, reasons


def _finish_selection(
    paths: list[str],
    runs: list[tuple[str, ...]],
    reasons: list[str],
    map_data: dict,
) -> Selection:
    if not runs:
        return _full_selection(paths, "无匹配规则 ⇒ 全量")
    selected_labels = {" ".join(run) for run in runs}
    skipped = [
        (label, "未变更")
        for label in _all_run_labels(map_data)
        if label not in selected_labels
    ]
    return Selection(
        mode="selected",
        changed=tuple(paths),
        commands=tuple(runs),
        skipped=tuple(skipped),
        reasons=tuple(reasons),
    )


def select(changed: list[str], map_data: dict) -> Selection:
    """改动路径 → 选测结果（未知即全量）。"""
    paths = [_norm(p) for p in changed if p.strip()]
    if not paths:
        return _full_selection(paths, "无改动但进入选测（异常）⇒ 全量")
    hit = _first_full_prefix(paths, map_data)
    if hit is not None:
        return _full_selection(paths, f"策略层/全量前缀：{hit} ⇒ 全量")
    collected = _collect_runs(paths, map_data)
    if isinstance(collected, str):
        return _full_selection(
            paths, f"无可用映射（未映射/策略层/未知语言包）：{collected} ⇒ 全量"
        )
    runs, reasons = collected
    return _finish_selection(paths, runs, reasons, map_data)


def assert_skipped_reasons(skipped: tuple[tuple[str, str], ...]) -> None:
    """跳过记账守卫：`tests/` 条目必须带理由（否则就是静默跳过）。"""
    for label, reason in skipped:
        if "tests/" in label and not reason.strip():
            raise RuntimeError(f"跳过的测试目标缺理由：{label}")


def _pytest_version() -> str:
    try:
        import pytest  # noqa: PLC0415 — 仅此处读版本，避免工具启动即 import 重库

        return str(pytest.__version__)
    except ImportError:  # pragma: no cover — 无 pytest 的环境只影响缓存键
        return "pytest-absent"


def fingerprint(changed: list[str], mode: str) -> str:
    """缓存指纹 = HEAD + 工作区脏状态 + 各改动文件内容 + pytest 版本。"""
    parts = [_git(["rev-parse", "HEAD"]).strip(), _git(["status", "--porcelain"]), mode,
             _pytest_version()]
    for path in changed:
        file_path = ROOT / path
        if file_path.is_file():
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            parts.append(f"{path}:{digest}")
        else:
            parts.append(f"{path}:missing")
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cached_exit(state: dict, fp: str, mode: str) -> int | None:
    """可复用则返回上次 exit code；全量档永不缓存。"""
    if mode != "selected":
        return None
    if state.get("fingerprint") != fp:
        return None
    code = state.get("exit")
    return code if isinstance(code, int) else None


def _append_log(record: dict, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _run_commands(commands: tuple[tuple[str, ...], ...], timeout: int) -> int:
    for run in commands:
        argv = [sys.executable, *run]
        print(f"[affected_tests] 运行: {' '.join(run)}", flush=True)
        started = time.perf_counter()
        proc = subprocess.run(argv, cwd=ROOT, timeout=timeout)
        took = time.perf_counter() - started
        print(f"[affected_tests] exit={proc.returncode} 用时 {took:.1f}s", flush=True)
        if proc.returncode != 0:
            return proc.returncode
    return 0


def _check_pytest_targets(run: list) -> list[str]:
    """pytest run 的参数检查：目标存在；{lang} 模板父目录存在。"""
    errors: list[str] = []
    for arg in run[2:]:
        text = str(arg)
        if text.startswith("-"):
            continue
        if "{lang}" in text:
            parent = Path(text.replace("{lang}", "placeholder")).parent
            if not (ROOT / parent).is_dir():
                errors.append(f"模板父目录不存在：{parent}")
        elif "/" in text and not (ROOT / text).exists():
            errors.append(f"pytest 目标不存在：{text}")
    return errors


def _check_run(run: list, where: str) -> list[str]:
    if not run:
        return [f"{where}: 空 run"]
    if run[0] == "-m":
        return [f"{where}: {error}" for error in _check_pytest_targets(run)]
    script = str(run[0])
    if not (ROOT / script).exists():
        return [f"{where}: 脚本不存在：{script}"]
    return []


def _check_full_prefixes(map_data: dict) -> list[str]:
    return [
        f"full_prefixes 不存在：{prefix}"
        for prefix in map_data.get("full_prefixes") or []
        if not (ROOT / str(prefix)).exists()
    ]


def _check_rule_runs(runs: list, where: str) -> list[str]:
    errors: list[str] = []
    for run in runs:
        errors.extend(_check_run(list(run), where))
    return errors


def _check_rule(rule: dict) -> list[str]:
    where = f"rule {rule.get('name')}"
    errors: list[str] = []
    prefixes = rule.get("prefixes") or []
    if not prefixes:
        errors.append(f"{where}: prefixes 为空")
    for prefix in prefixes:
        if not (ROOT / str(prefix)).exists():
            errors.append(f"{where}: 前缀路径不存在：{prefix}")
    if not rule.get("self_tests") and not rule.get("runs"):
        errors.append(f"{where}: runs 为空")
    errors.extend(_check_rule_runs(rule.get("runs") or [], where))
    return errors


def _check_suffix_rule(suffix_rule: dict) -> list[str]:
    where = f"suffix_rule {suffix_rule.get('name')}"
    errors: list[str] = []
    if not suffix_rule.get("suffixes"):
        errors.append(f"{where}: suffixes 为空")
    if not suffix_rule.get("runs"):
        errors.append(f"{where}: runs 为空")
    errors.extend(_check_rule_runs(suffix_rule.get("runs") or [], where))
    return errors


def audit_map(map_data: dict) -> list[str]:
    """映射表健康：路径存在、条目非空、目标存在（CI 只跑这一项）。"""
    errors = _check_full_prefixes(map_data)
    for rule in _map_rules(map_data):
        errors.extend(_check_rule(rule))
    for suffix_rule in map_data.get("suffix_rule") or []:
        errors.extend(_check_suffix_rule(suffix_rule))
    return errors


def _selection_json(selection: Selection, fp: str, cached: bool) -> dict:
    return {
        "mode": selection.mode,
        "changed": list(selection.changed),
        "commands": [list(run) for run in selection.commands],
        "skipped": [{"target": label, "reason": reason} for label, reason in selection.skipped],
        "reasons": list(selection.reasons),
        "fingerprint": fp,
        "cached": cached,
    }


def _print_selection(selection: Selection, fp: str) -> None:
    print(
        f"[affected_tests] mode={selection.mode} selected={len(selection.commands)} "
        f"skipped={len(selection.skipped)} fp={fp[:12]}"
    )
    for reason in selection.reasons:
        print(f"  · {reason}")
    for label, reason in selection.skipped:
        print(f"  - skipped {label}（{reason}）")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="affected_tests",
        description=(__doc__ or "affected_tests").splitlines()[0],
    )
    parser.add_argument("--full", action="store_true", help="强制全量（不缓存）")
    parser.add_argument("--audit-map", action="store_true", help="映射表健康检查（CI 用）")
    parser.add_argument("--since", default=None, help="与指定 git ref 对比（默认 HEAD+未跟踪）")
    parser.add_argument("--simulate-changed", default=None, help="演练：逗号分隔改动路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印选择，不执行")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="缓存状态文件")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="选择账本（JSONL）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单条命令超时秒数")
    return parser.parse_args(argv)


def _changed_from_args(args: argparse.Namespace) -> list[str]:
    if args.simulate_changed is not None:
        return [_norm(part.strip()) for part in args.simulate_changed.split(",") if part.strip()]
    return changed_paths(args.since)


def _selection(args: argparse.Namespace, map_data: dict) -> Selection:
    changed = _changed_from_args(args)
    if args.full:
        return _full_selection(changed, "强制全量（--full）")
    return select(changed, map_data)


def _cached_or_none(selection: Selection, fp: str, args: argparse.Namespace) -> int | None:
    """无变化复用上次结果（全量/dry-run 不走缓存）。"""
    if args.full or args.dry_run:
        return None
    state = _load_json(args.state)
    cached = cached_exit(state, fp, selection.mode)
    if cached is None:
        return None
    record = _selection_json(selection, fp, True)
    record["exit"] = cached
    print(
        f"[affected_tests] 无变化（HEAD+工作区+未跟踪+pytest 指纹一致），"
        f"复用上次结果 exit={cached}（{state.get('ts', '?')}）"
    )
    if args.json:
        print(json.dumps(record, ensure_ascii=False))
    _append_log({"ts": _now(), "mode": selection.mode, "cached": True,
                 "exit": cached, "fingerprint": fp}, args.log)
    return cached


def _dry_run(selection: Selection, fp: str, args: argparse.Namespace) -> int:
    record = _selection_json(selection, fp, False)
    record["exit"] = 0
    if args.json:
        print(json.dumps(record, ensure_ascii=False))
    _append_log({"ts": _now(), "mode": selection.mode, "cached": False,
                 "dry_run": True, "exit": 0, "fingerprint": fp,
                 "changed": list(selection.changed)}, args.log)
    return 0


def _execute(selection: Selection, fp: str, args: argparse.Namespace) -> int:
    code = _run_commands(selection.commands, args.timeout)
    record = _selection_json(selection, fp, False)
    record["exit"] = code
    if args.json:
        print(json.dumps(record, ensure_ascii=False))
    _append_log({"ts": _now(), "mode": selection.mode, "cached": False,
                 "exit": code, "fingerprint": fp, "changed": list(selection.changed),
                 "commands": [list(run) for run in selection.commands],
                 "skipped": len(selection.skipped)}, args.log)
    if selection.mode == "selected" and not args.full:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(
            json.dumps({"ts": _now(), "fingerprint": fp, "exit": code,
                        "mode": selection.mode,
                        "commands": [list(run) for run in selection.commands]},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    map_data = _load_map()
    if args.audit_map:
        errors = audit_map(map_data)
        for error in errors:
            print(f"[affected_tests] {error}")
        print(f"[affected_tests] 映射表健康：{'OK' if not errors else f'{len(errors)} 项违规'}")
        return 0 if not errors else 2
    selection = _selection(args, map_data)
    fp = fingerprint(list(selection.changed), selection.mode) if selection.mode == "selected" else ""
    cached = _cached_or_none(selection, fp, args)
    if cached is not None:
        return cached
    assert_skipped_reasons(selection.skipped)
    _print_selection(selection, fp)
    if args.dry_run:
        return _dry_run(selection, fp, args)
    return _execute(selection, fp, args)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
