"""check_registry.py — 声明式检查规则表（[[checks]]，规则=数据）。

诊断链自定义层的 L1 声明层（ADR-0004 / analyzer/semantic_checks.md §3）：
规则以 TOML `[[checks]]` 数组声明在语言包插件目录的 `rules/*.toml`，
引擎只做加载/校验/分发——规则行为（pattern/kind 匹配、message 模板、
severity）全部来自数据，零语言知识进代码。

规则 schema（字段说明见 analyzer/semantic_checks.md §3）：
    [[checks]]
    id = "NC001"                 # 全局唯一（前缀=分类）
    category = "naming"          # 分类：width / naming / race / cdc / style…
    severity = "warning"         # error / warning / info
    scope = ["rtl", "tb"]        # 适用作用域（后续与用户配置 per_file 叠加）
    message = "module {name} 不符合 {pattern}"   # 模板，{var} 插值
    kind = "module"              # 分发键：符号种类（module/wire/reg/port/…）
    pattern = "^[a-z][a-z0-9_]*$"  # 声明式判定：正则匹配符号名（纯声明式
                                 #   规则的核心；缺省 = 仅靠 kind 分发，
                                 #   由 handler 脚本做更复杂判定）
    # handler = "_name_check.py:check_module"  # L2 脚本兜底（可选）

fail-fast（ADR-0003）：id 重复 / severity 非法 / pattern 非法正则 /
kind 缺失 → 直接报错，不静默降级。
Doc: analyzer/semantic_checks.md（语义检查插槽：L1 声明层）
"""

from __future__ import annotations

import os
import re
import tomllib
from typing import Any

from core.errors import ConfigError

# ── 全局规则表（按 plugins_dir 键控；与 plugin_loader 组件表同生命周期，
#    由 core/global_state.py 快照/还原）───────────────────────────────
_CHECK_RULES: dict[str, list[dict[str, Any]]] = {}

_SEVERITIES = {"error", "warning", "info"}


def discover_rule_files(plugins_dir: str = "") -> list[str]:
    """递归扫描插件目录树下的 `rules/*.toml`（聚类目录支持）。

    plugins_dir 非空时用指定语言包的 plugins/（单语言选择）；空时用默认包。
    返回规则文件路径列表（排序稳定）。与 plugin_loader.discover_components
    同语义：任意深度子目录均可作为聚类容器，rules/ 目录随组件所在位置。
    """
    comp_dir = _resolve_plugins_dir(plugins_dir)
    if not comp_dir or not os.path.isdir(comp_dir):
        return []
    files: list[str] = []
    for root, dirs, fnames in os.walk(comp_dir):
        # 跳过私有目录（_ 前缀，如 __pycache__）
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        if os.path.basename(root) != "rules":
            continue
        for fname in sorted(fnames):
            if fname.endswith(".toml"):
                files.append(os.path.join(root, fname))
    return files


def _resolve_plugins_dir(plugins_dir: str) -> str:
    """解析插件目录（绝对路径；默认包 plugins/）。"""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if plugins_dir:
            abs_dir = (
                plugins_dir
                if os.path.isabs(plugins_dir)
                else os.path.join(root, plugins_dir)
            )
            return abs_dir if os.path.isdir(abs_dir) else ""
        from core.define import DEFAULT_RULES_DIR

        pdir = os.path.join(root, DEFAULT_RULES_DIR, "plugins")
        return pdir if os.path.isdir(pdir) else ""
    except OSError:
        return ""


def load_check_rules(plugins_dir: str = "") -> list[dict[str, Any]]:
    """加载插件目录全部 `rules/*.toml` 的 [[checks]]，校验并注册。

    幂等：同一 plugins_dir 已加载则直接返回缓存（规则表是静态数据，
    重复加载无意义且重复注册会误报 id 冲突）。
    校验（fail-fast，ADR-0003）：
        - [[checks]] 必须存在且为数组
        - id 必填、全局唯一（跨文件）
        - severity ∈ {error, warning, info}
        - kind 必填（声明式分发键——规则按符号种类匹配）
        - pattern 若提供必须是合法正则
        - message 必填（模板，report 时插值）
    """
    key = _resolve_plugins_dir(plugins_dir)
    if key in _CHECK_RULES:
        return _CHECK_RULES[key]

    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in discover_rule_files(plugins_dir):
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        entries = raw.get("checks") or []
        if not isinstance(entries, list):
            raise ConfigError(
                f"[checks] 规则文件 {path} 缺 [[checks]] 数组（顶层 checks 应为列表）"
            )
        rule_dir = os.path.dirname(path)  # 插件 rules/ 目录（handler 相对定位）
        for entry in entries:
            _validate_rule(entry, path, seen_ids)
            entry.setdefault("_dir", rule_dir)
            rules.append(entry)
    _CHECK_RULES[key] = rules
    return rules


def _validate_rule(entry: dict, path: str, seen_ids: set[str]) -> None:
    """单条规则校验（fail-fast）。"""
    rid = entry.get("id")
    if not isinstance(rid, str) or not rid:
        raise ConfigError(f"[checks] {path}: 规则缺 id（{entry!r}）")
    if rid in seen_ids:
        raise ConfigError(f"[checks] {path}: 规则 id '{rid}' 重复（全局唯一）")
    seen_ids.add(rid)

    severity = entry.get("severity", "warning")
    if severity not in _SEVERITIES:
        raise ConfigError(
            f"[checks] {path}: 规则 '{rid}' severity '{severity}' 非法"
            f"（应为 {'/'.join(sorted(_SEVERITIES))}）"
        )

    kind = entry.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ConfigError(
            f"[checks] {path}: 规则 '{rid}' 缺 kind（声明式分发键）"
        )

    pattern = entry.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise ConfigError(f"[checks] {path}: 规则 '{rid}' pattern 应为字符串")
        try:
            re.compile(pattern)
        except re.error as e:
            raise ConfigError(
                f"[checks] {path}: 规则 '{rid}' pattern 非法正则: {e}"
            ) from e

    if not entry.get("message"):
        raise ConfigError(f"[checks] {path}: 规则 '{rid}' 缺 message（报告模板）")

    default = entry.get("default", True)
    if not isinstance(default, bool):
        raise ConfigError(f"[checks] {path}: 规则 '{rid}' default 应为布尔值")


def get_check_rules(plugins_dir: str = "") -> list[dict[str, Any]]:
    """返回已加载的规则表（未加载时自动加载）。"""
    key = _resolve_plugins_dir(plugins_dir)
    if key not in _CHECK_RULES:
        load_check_rules(plugins_dir)
    return _CHECK_RULES.get(key, [])


def get_rules_for_kind(kind: str, plugins_dir: str = "") -> list[dict[str, Any]]:
    """按符号种类取适用规则（kind 分发——svlint naming 族蓝本）。"""
    return [r for r in get_check_rules(plugins_dir) if r.get("kind") == kind]


def get_rule(rule_id: str, plugins_dir: str = "") -> dict[str, Any] | None:
    """按 id 取规则（用户配置 enabled/overrides 引用）。"""
    for r in get_check_rules(plugins_dir):
        if r.get("id") == rule_id:
            return r
    return None


# ── P4 用户配置层（config/tpc_config.json 的 checks 段）──────────────
#
# 语义（analyzer/semantic_checks.md §4，Ruff/Semgrep 共识）：
#     enabled   = ["NC001", ...]              # 未列出 = 关闭（"不选即关"）
#     overrides = { "NC001": { "severity": "error" } }   # severity 提升/降级
#     per_file  = { "tb/**": { "disabled": ["NC001"] } } # 文件 glob 豁免
# 未配置 checks 段（或 enabled 缺省）→ 全部规则启用（向后兼容 P3 行为）。
# fail-fast（ADR-0003）：enabled/overrides 引用不存在的规则 id、severity
# 非法、per_file 键非 glob → 直接报错，不静默降级。

_USER_CONFIG_CACHE: dict[str, dict | None] = {}
"""按配置文件路径缓存解析结果（None = 无 checks 段）。"""


def load_user_check_config(plugins_dir: str = "") -> dict:
    """读取用户项目配置的 checks 段（config/tpc_config.json）。

    Returns:
        dict: {
            "enabled": list[str] | None,   # None = 全部启用（未配置）
            "overrides": dict,             # {id: {"severity": ...}}
            "per_file": dict,              # {glob: {"disabled": [id, ...]}}
        }
        无用户配置文件或无 checks 段 → 全空（全部规则启用，P3 行为）。

    三段各自一个校验函数（`_validate_enabled` / `_validate_overrides` /
    `_validate_per_file`）：都 fail-fast，且都要求规则 id 引用存在
    （`_validate_rule_refs`）。
    """
    from core._user_config import find_user_config

    path = find_user_config()
    if not path:
        return {}
    if path in _USER_CONFIG_CACHE:
        return _USER_CONFIG_CACHE[path] or {}

    checks = _load_user_checks(path)
    if checks is None:
        _USER_CONFIG_CACHE[path] = None
        return {}

    plugins_dir = _resolve_plugins_dir(plugins_dir)
    # 校验前确保规则表已加载（用户配置引用校验需要可用规则 id 全集）
    rule_ids = _user_rule_ids(plugins_dir)

    enabled = _validate_enabled(checks.get("enabled"), rule_ids, path)
    overrides = _validate_overrides(checks.get("overrides", {}), rule_ids, path)
    per_file = _validate_per_file(checks.get("per_file", {}), rule_ids, path)

    result = {"enabled": enabled, "overrides": overrides, "per_file": per_file}
    _USER_CONFIG_CACHE[path] = result
    return result


def _load_user_checks(path: str) -> dict | None:
    """读用户配置文件 → checks 段 dict；文件缺失/解析失败/无 checks 段 → None。"""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    checks = raw.get("checks") if isinstance(raw, dict) else None
    if not isinstance(checks, dict):
        return None
    return checks


def _user_rule_ids(plugins_dir: str) -> set[str]:
    """规则 id 全集（用户配置引用校验用）；调用前确保规则表已加载。"""
    rules = get_check_rules(plugins_dir)
    return {rid for rid in (r.get("id") for r in rules) if isinstance(rid, str)}


def _validate_enabled(enabled, rule_ids: set[str], path: str) -> list[str] | None:
    """enabled：规则 id 列表（None = 未配置 → 全部启用）。"""
    if enabled is None:
        return None
    if not isinstance(enabled, list) or not all(
        isinstance(x, str) for x in enabled
    ):
        raise ConfigError(
            f"[checks] 用户配置 enabled 应为规则 id 列表（{path}）"
        )
    _validate_rule_refs(enabled, rule_ids, "enabled", path)
    return enabled


def _validate_overrides(overrides, rule_ids: set[str], path: str) -> dict:
    """overrides：{规则 id: {"severity": ...}}——id 须存在、severity 须合法。"""
    if not isinstance(overrides, dict):
        raise ConfigError(f"[checks] 用户配置 overrides 应为 dict（{path}）")
    for rid, ov in overrides.items():
        _validate_rule_refs([rid], rule_ids, "overrides", path)
        if not isinstance(ov, dict):
            raise ConfigError(
                f"[checks] 用户配置 overrides[{rid}] 应为 dict（{path}）"
            )
        sev = ov.get("severity")
        if sev is not None and sev not in _SEVERITIES:
            raise ConfigError(
                f"[checks] 用户配置 overrides[{rid}] severity '{sev}' 非法"
                f"（应为 {'/'.join(sorted(_SEVERITIES))}，{path}）"
            )
    return overrides


def _validate_per_file(per_file, rule_ids: set[str], path: str) -> dict:
    """per_file：{文件 glob: {"disabled": [规则 id, ...]}}——键与值形态都校验。"""
    if not isinstance(per_file, dict):
        raise ConfigError(f"[checks] 用户配置 per_file 应为 dict（{path}）")
    for glob_pat, spec in per_file.items():
        if not isinstance(glob_pat, str) or not glob_pat:
            raise ConfigError(
                f"[checks] 用户配置 per_file 键应为文件 glob（{path}）"
            )
        if not isinstance(spec, dict):
            raise ConfigError(
                f"[checks] 用户配置 per_file[{glob_pat}] 应为 dict（{path}）"
            )
        disabled = spec.get("disabled", [])
        if not isinstance(disabled, list) or not all(
            isinstance(x, str) for x in disabled
        ):
            raise ConfigError(
                f"[checks] 用户配置 per_file[{glob_pat}].disabled 应为规则"
                f" id 列表（{path}）"
            )
        _validate_rule_refs(disabled, rule_ids, f"per_file[{glob_pat}]", path)
    return per_file

def _validate_rule_refs(ids: list[str], rule_ids: set[str], where: str, path: str) -> None:
    """校验规则 id 引用存在（fail-fast：引用不存在的规则 = 配置错误）。"""
    missing = [i for i in ids if i not in rule_ids]
    if missing:
        raise ConfigError(
            f"[checks] 用户配置 {where} 引用不存在的规则 id: {missing}"
            f"（{path}；可用规则: {sorted(rule_ids)}）"
        )
