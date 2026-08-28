"""check_registry.py — 声明式检查规则表（[[checks]]，规则=数据）。

诊断链自定义层的 L1 声明层（ADR-0004 / semantic_checks.md §3）：
规则以 TOML `[[checks]]` 数组声明在语言包插件目录的 `rules/*.toml`，
引擎只做加载/校验/分发——规则行为（pattern/kind 匹配、message 模板、
severity）全部来自数据，零语言知识进代码。

规则 schema（字段说明见 docs/semantic_checks.md §3）：
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
Doc: docs/semantic_checks.md（语义检查插槽：L1 声明层）
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
    """扫描插件目录下的 `rules/*.toml`（每个插件可选一个 rules/ 目录）。

    plugins_dir 非空时用指定语言包的 plugins/（单语言选择）；空时用默认包。
    返回规则文件路径列表（排序稳定）。
    """
    comp_dir = _resolve_plugins_dir(plugins_dir)
    if not comp_dir or not os.path.isdir(comp_dir):
        return []
    files: list[str] = []
    for name in sorted(os.listdir(comp_dir)):
        cdir = os.path.join(comp_dir, name)
        if not os.path.isdir(cdir) or name.startswith("_"):
            continue
        rules_dir = os.path.join(cdir, "rules")
        if not os.path.isdir(rules_dir):
            continue
        for fname in sorted(os.listdir(rules_dir)):
            if fname.endswith(".toml"):
                files.append(os.path.join(rules_dir, fname))
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
