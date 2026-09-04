"""checks.py — 声明式检查规则执行器（L1 声明层，规则=数据）。

在 analyzer 遍历结束后（post-pass 时机，与 inst_check 同形态）对
已收集的符号表按 kind 分发 [[checks]] 规则表，pattern 判定 + message
模板插值，向 context.report 报诊断。

零语言知识：kind 分发键、pattern、message 全部来自语言包插件目录
`rules/*.toml`（core/check_registry 加载）。引擎只做通用执行——
符号 kind 与规则 kind 字符串匹配、正则判定、{var} 模板插值。

执行时机：AnalysisTraversal._run_postpasses 之后由框架调用
（check_rules_pass）；也可被插件 postpass 显式调用（fn(analyzer, ctx)）。

规则形态（两种，可并存）：
    1. 纯声明式：kind + pattern（正则匹配符号名）——引擎直接判定
    2. handler 兜底：规则带 handler 字段（"file.py:fn"，L2 脚本），
       声明式 pattern 判定不足以表达时由脚本做复杂判定；脚本签名
       fn(symbol, rule, context) -> str | None（返回 None = 通过，
       返回消息文本 = 报诊断；消息可含 {var} 由引擎统一插值）
Doc: analyzer/semantic_checks.md（L1 声明式 schema + 执行器）
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from core.check_registry import (
    get_check_rules,
    get_rules_for_kind,
    load_user_check_config,
)
from core.define import Node

# handler 缓存：{插件目录: {规则 id: (module, fn)}}——handler 是插件
# 目录内脚本（_name_check.py:check_module），跨 analyze 复用模块对象
# （与 plugin_loader._load_python_handlers 同幂等语义）。
_HANDLER_CACHE: dict[str, dict[str, tuple[Any, Callable]]] = {}


def plugins_dir_of(analyzer) -> str:
    """analyzer 的语言包插件目录（无 rules_dir 时为空串）。"""
    rules_dir = getattr(analyzer, "_rules_dir", None)
    if not rules_dir:
        return ""
    return os.path.join(rules_dir, "plugins")


def active_rule_ids(analyzer) -> set:
    """当前启用的规则 id 集合（postpass 插件复用同一激活逻辑）。

    注入（analyzer._checks_enabled，评测/测试显式启用）> 用户配置显式
    enabled（"不选即关"）> default=true 的规则 ∪ 被 overrides/per_file
    引用的规则（引用即启用）。规则 id 全量来自 [[checks]] 注册表。
    """
    injected = getattr(analyzer, "_checks_enabled", None)
    if injected is not None:
        return set(injected)
    pdir = plugins_dir_of(analyzer)
    user_cfg = load_user_check_config(plugins_dir=pdir)
    enabled = user_cfg.get("enabled")
    if enabled is not None:
        return set(enabled)
    referenced = set(user_cfg.get("overrides", {})) | {
        rid
        for spec in user_cfg.get("per_file", {}).values()
        for rid in (spec or {}).get("disabled", [])
    }
    active = {
        r.get("id", "")
        for r in get_check_rules(plugins_dir=pdir)
        if r.get("default", True)
    }
    active |= referenced
    return active


def check_rules_pass(analyzer, context) -> None:
    """postpass 入口：遍历后对所有符号按 kind 分发声明式规则。

    从 analyzer.all_symbols（遍历期 symbol_declare 原语收集）取符号，
    按 sym.kind 查规则表，pattern 判定 / handler 兜底，报诊断。
    无规则表（语言包未声明 rules/）时零开销返回。
    规则表定位：analyzer._rules_dir（grammar/<lang>/）下的 plugins/；
    未指定（None）用默认包。

    P4 用户配置（config/tpc_config.json checks 段）在此应用：
        enabled   未列出 = 关闭（"不选即关"）；缺省 = 全部启用
        overrides severity 覆盖（如 NC001 → error）
        per_file  文件 glob 豁免（disabled 列表）
    """
    symbols = getattr(analyzer, "all_symbols", None) or []
    if not symbols:
        return
    plugins_dir = plugins_dir_of(analyzer)
    user_cfg = load_user_check_config(plugins_dir=plugins_dir)
    overrides = user_cfg.get("overrides", {})
    per_file = user_cfg.get("per_file", {})
    file_ctx = _file_context(symbols)
    active = active_rule_ids(analyzer)

    # 规则表按插件目录加载（语言包 rules/）；缓存由 check_registry 管理
    for sym in symbols:
        rules = get_rules_for_kind(sym.kind, plugins_dir=plugins_dir)
        if not rules:
            continue
        name = getattr(sym, "name", "") or ""
        if not name:
            continue
        for rule in rules:
            rid = rule.get("id", "")
            if rid not in active:
                continue  # 未启用（默认关 / 不选即关）
            if _disabled_for_file(rid, sym, file_ctx, per_file):
                continue  # per_file 豁免
            rule = _with_override(rule, overrides.get(rid))
            _apply_rule(sym, rule, name, context)


def _file_context(symbols) -> str | None:
    """取符号文件的代表路径（per_file glob 匹配用）。

    ProjectChecker 路径给节点挂了 _file；单文件 analyze 无文件上下文
    （None = 不参与 per_file 豁免）。取第一个有 _file 的符号。
    """
    for sym in symbols:
        node = getattr(sym, "decl_node", None)
        f = getattr(node, "_file", None)
        if f:
            return f
    return None


def _disabled_for_file(rid: str, sym, file_ctx: str | None, per_file: dict) -> bool:
    """per_file glob 豁免：符号文件匹配 glob → disabled 含 rid → 跳过。"""
    if not per_file or not file_ctx:
        return False
    for glob_pat, spec in per_file.items():
        disabled = (spec or {}).get("disabled", [])
        if rid not in disabled:
            continue
        if _glob_match(glob_pat, file_ctx):
            return True
    return False


def _glob_match(glob_pat: str, path: str) -> bool:
    """文件 glob 匹配（路径尾部语义，同 pathlib.PurePath.match）。

    pattern 是相对 glob（如 `tb/*.sv`、`**/tb_*.v`）——匹配文件路径的
    尾部（不要求从根锚定），符合 Ruff per-file-ignores 语义。`**` 递归
    段通配。Windows 路径反斜杠归一为 `/`。
    """
    from pathlib import PurePosixPath

    pat = glob_pat.replace("\\", "/").strip("/")
    norm = path.replace("\\", "/")
    if not pat:
        return False
    # ** 递归：拆成前缀段 + 尾部模式，任一尾部匹配即豁免
    if "**" in pat:
        head, _, tail = pat.partition("**")
        head = head.strip("/")
        tail = tail.strip("/")
        if tail:
            return PurePosixPath(norm).match("*" + tail) or (
                PurePosixPath(norm).match(tail) if "/" in tail else PurePosixPath(norm).name == tail
            )
        # 纯 ** 前缀：匹配任意深度的尾部段
        return PurePosixPath(norm).match(head + "*")
    # 相对 glob：路径尾部匹配（把 pattern 作为尾部后缀，前面任意）
    return PurePosixPath(norm).match(pat) or PurePosixPath(norm).match(
        "*" + ("/" + pat if "/" in pat else "")
    )


def _with_override(rule: dict, override: dict | None) -> dict:
    """应用用户 severity 覆盖（规则副本，不改全局表）。"""
    if not override:
        return rule
    merged = dict(rule)
    sev = override.get("severity")
    if sev:
        merged["severity"] = sev
    return merged


def _apply_rule(sym, rule: dict, name: str, context) -> None:
    """对单个符号应用单条规则（pattern 判定 / handler 兜底）。"""
    rid = rule.get("id", "")
    severity = rule.get("severity", "warning")
    message_tpl = rule.get("message", "")

    pattern = rule.get("pattern")
    if pattern:
        if re.match(pattern, name):
            return  # 通过
        context.report(
            _interpolate(message_tpl, sym, name, rule),
            code=rid,
            level=severity,
            node=sym.decl_node,
        )
        return

    handler_spec = rule.get("handler")
    if handler_spec:
        msg = _call_handler(handler_spec, rule, sym, context)
        if msg:
            context.report(
                _interpolate(msg, sym, name, rule),
                code=rid,
                level=severity,
                node=sym.decl_node,
            )
        return

    # 既无 pattern 也无 handler：纯 kind 分发规则（仅登记不判定）——
    # 允许（如分类占位规则），引擎零判定。
    return


def _interpolate(tpl: str, sym, name: str, rule: dict) -> str:
    """message 模板插值：{name} / {kind} / {pattern} / {id} / {severity}。

    未知占位符原样保留（不抛错——模板是语言包数据，缺字段不该炸引擎）。
    """
    mapping = {
        "name": name,
        "kind": getattr(sym, "kind", ""),
        "pattern": rule.get("pattern", ""),
        "id": rule.get("id", ""),
        "severity": rule.get("severity", ""),
    }
    try:
        return tpl.format(**mapping)
    except (KeyError, IndexError, ValueError):
        return tpl


def _call_handler(handler_spec: str, rule: dict, sym, context) -> str | None:
    """调用 L2 脚本 handler（'file.py:fn'），返回消息文本或 None。

    handler 签名：fn(symbol, rule, context) -> str | None
    （返回 None = 通过；str = 诊断消息，引擎统一插值 + 报告）。
    fail-fast：声明了但模块/函数缺失直接报错（ADR-0003），
    不静默降级（静默 = 检查静默失效，比报错更危险）。
    """
    if ":" not in handler_spec:
        raise ValueError(
            f"[checks] handler 声明格式应为 'file.py:fn'，收到: {handler_spec!r}"
        )
    fname, fn_name = handler_spec.split(":", 1)
    # handler 模块路径：相对插件 rules/ 所在目录（规则文件旁），按
    # core/plugin_loader._load_python_handlers 同形态加载
    rule_dir = _rule_dir_of(rule)
    fn = _get_handler_fn(rule_dir, fname, fn_name)
    return fn(sym, rule, context)


def _rule_dir_of(rule: dict) -> str:
    """规则来源目录（check_registry 加载时未记录路径，从规则字段反查）。"""
    return rule.get("_dir", "")


def _get_handler_fn(rule_dir: str, fname: str, fn_name: str) -> Callable:
    """按 (插件目录, file.py, fn) 解析 handler 函数（带缓存，幂等）。"""
    if not rule_dir:
        raise ValueError("[checks] 规则缺 _dir（handler 需要相对插件目录定位）")
    import importlib.util
    import os
    import sys

    key = rule_dir
    cache = _HANDLER_CACHE.setdefault(key, {})
    cache_key = f"{fname}:{fn_name}"
    if cache_key in cache:
        return cache[cache_key][1]

    hpath = os.path.join(rule_dir, fname)
    if not os.path.isfile(hpath):
        raise ValueError(f"[checks] handler 模块不存在: {hpath}")
    mod_name = f"_checks_{os.path.basename(rule_dir)}_{fname.replace('.', '_')}"
    if mod_name in sys.modules:
        mod = sys.modules[mod_name]
    else:
        spec = importlib.util.spec_from_file_location(mod_name, hpath)
        if not spec or not spec.loader:
            raise ValueError(f"[checks] handler 模块加载失败: {hpath}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        raise ValueError(
            f"[checks] handler 函数 {fn_name} 不存在于 {fname}（{hpath}）"
        )
    cache[cache_key] = (mod, fn)
    return fn


def run_declarative_checks(analyzer, context) -> None:
    """别名：与 check_rules_pass 相同（供插件 postpasses 显式声明）。"""
    check_rules_pass(analyzer, context)
