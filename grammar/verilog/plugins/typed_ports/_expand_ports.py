"""_expand_ports.py — role 端口集递归展开器（typed_ports 组件内 analyzer postpass）。

在 analyze 遍历结束后（scope 树已全量、所有 type/role 符号已声明）对每个 role
递归展开其**完整端口集**（nested 嵌套 + invert 对侧），写入符号
`sym.attrs["resolved_ports"]`——下游（_transform._resolved_ports / 映射表构建）
统一读此键，避免各消费点重复解析、并修复 analyze 即时 resolve 的缺陷：

    L2 嵌套反转：invert 目标含嵌套端口时，嵌套须取对侧 role 展开（此前 raw
       端口未递归 → 嵌套端口静默缺失）
    L3 后置定义：invert/nested 目标 role 定义在后时，analyze 单遍 DFS 即时
       resolve 取不到（此前无回调）——postpass 在遍历结束后跑，scope 全量无
       时序问题

语义（作者 2026-09-08 拍板）：invert = 取对侧角色。role 定义体若是纯
`invert X` 声明 → 展开 = X 端口集逐项取反（invert_role）；嵌套端口 (T.X inner)
在取反语境下用 T.X 的对侧角色（T 内 `Y: invert X` 的 Y）展开，无显式对侧则
递归取反。

语言知识（nested/invert 形态 + 对侧查找）全在本插件层；引擎零硬编码。
执行：typed_ports tpc.toml [analyzer] postpasses 追加本模块。
"""

from __future__ import annotations

from core._protocol import ROW_ORIGIN
from core.define import Node

# 方向反转映射（_invert_map.py 旧原语已删，本常量集中定义普通端口逐项取反）
_DIR_INV = {"input": "output", "output": "input", "inout": "inout"}

_ANSI = ("AnsiInputDecl", "AnsiOutputDecl", "AnsiInoutDecl")


def run_expand_ports(analyzer, context) -> None:
    """postpass 入口：遍历 scope 树，对每个 role 递归展开完整端口集。

    产出：sym.attrs["resolved_ports"] = [{direction, name, packed_range?, origin}, ...]
          origin = 展开路径链（`spi.slave > invert(spi.master) > #miso`），
          供映射表来源追踪（ADR-0015 §2），非消费字段。
    幂等：同一 scope 树多次跑结果一致（从 raw ports 重新展开，不依赖残留）。
    """
    del context  # postpass 协议签名参数，本 postpass 不消费诊断通道
    root = getattr(analyzer, "root_scope", None)
    if root is None:
        return
    type_scopes = _collect_type_scopes(root)
    for tname, tsc in type_scopes.items():
        for sym in tsc.symbols.values():
            if getattr(sym, "kind", "") != "role":
                continue
            # 无条件写键（空展开也写 []）：所有 role 一致带 resolved_ports，
            # 下游消费点（_check/_transform/_semantic_mapping）只读此键即可，
            # 不再需要 _ref_callbacks 中间层回退（P1.5 step 2 清理）。
            # 每行携带 origin（来源路径链，ADR-0015 §2 映射表来源追踪）：
            # `spi.slave > invert(spi.master) > #miso` —— 展开段序列 +
            # 源端口名，供可视化管道回答“这行从哪来”。
            sym.attrs["resolved_ports"] = _expand_role(
                type_scopes, tname, sym.name, (), f"{tname}.{sym.name}"
            )


# ── 递归展开核心 ─────────────────────────────────────


def _expand_role(type_scopes: dict, type_name: str, role_name: str,
                 _stack: tuple = (), chain: str = "") -> list[dict]:
    """按 role 定义体展开端口集（非反转视角）。

    定义体若是纯 `invert X` → 取 X 的取反（invert_role）；否则普通展开：
    Ansi 端口原方向；TypeNestedPort → 递归展开目标 role + 实例名前缀。

    chain: 展开路径链（可视化溯源）；空则自建起点段 `类型.角色`。
    """
    key = ("e", type_name, role_name)
    if key in _stack:
        return []
    _stack = _stack + (key,)
    chain = chain or f"{type_name}.{role_name}"
    raw = _role_raw_ports(type_scopes, type_name, role_name)
    if raw is None:
        return []
    # 纯 invert 声明：`slave: invert master` → invert_role(master)
    if len(raw) == 1 and raw[0].get("node_name") == "TypeInvertPort":
        target = raw[0].get("target_role", "")
        return _invert_role(type_scopes, type_name, target, _stack,
                            f"{chain} > invert({type_name}.{target})")
    out: list[dict] = []
    for p in raw:
        nn = p.get("node_name", "")
        if nn in _ANSI:
            _append_ansi(out, p, chain=chain)
        elif nn == "TypeNestedPort":
            ts = p.get("type_spec") or {}
            tname = ts.get("type_name", "")
            rname = ts.get("role_name", "")
            prefix = p.get("instance_name", "")
            for e in _expand_role(type_scopes, tname, rname, _stack,
                                 f"{chain} > nested({prefix}:{tname}.{rname})"):
                e2 = _rename_port(e, prefix)
                out.append(e2)
        elif nn == "TypeInvertPort":
            # role 体内混用 invert Z（非纯反转定义）→ 该项取 Z 的对侧
            target = p.get("target_role", "")
            out.extend(_invert_role(type_scopes, type_name, target, _stack,
                                    f"{chain} > invert({type_name}.{target})"))
    return out


def _rename_port(entry: dict, prefix: str) -> dict:
    """嵌套端口实例名前缀化（name 与 origin 同步）。

    origin 保持"展开链 … > #源端口名"形态：rename 段插在 `#` 之前，
    终点恒为源端口锚点（改名事实由 rename 段表达）。
    """
    e2 = dict(entry)
    if prefix and e2.get("name"):
        e2["name"] = f"{prefix}_{e2['name']}"
        o = e2.get(ROW_ORIGIN)
        if o:
            head, sep, tail = o.rpartition(" > #")
            e2[ROW_ORIGIN] = (
                f"{head} > rename({prefix}){sep}{tail}" if sep
                else f"{o} > rename({prefix})"
            )
    return e2


def _invert_role(type_scopes: dict, type_name: str, role_name: str,
                 _stack: tuple = (), chain: str = "") -> list[dict]:
    """取 role 的对侧端口集：普通端口方向反转 + 嵌套取对侧角色展开。"""
    key = ("i", type_name, role_name)
    if key in _stack:
        return []
    _stack = _stack + (key,)
    chain = chain or f"{type_name}.{role_name}"
    raw = _role_raw_ports(type_scopes, type_name, role_name)
    if raw is None:
        return []
    out: list[dict] = []
    for p in raw:
        nn = p.get("node_name", "")
        if nn in _ANSI:
            _append_ansi(out, p, invert=True, chain=chain)
        elif nn == "TypeNestedPort":
            ts = p.get("type_spec") or {}
            tname = ts.get("type_name", "")
            rname = ts.get("role_name", "")
            prefix = p.get("instance_name", "")
            sub = _opposite_expand(type_scopes, tname, rname, _stack,
                                   f"{chain} > opposite({prefix}:{tname}.{rname})")
            for e in sub:
                out.append(_rename_port(e, prefix))
        elif nn == "TypeInvertPort":
            # 混用 invert（罕见）：目标 Z 的对侧 = 展开 Z 的定义（若纯反转已含）
            target = p.get("target_role", "")
            out.extend(_expand_role(type_scopes, type_name, target, _stack,
                                    f"{chain} > invert({type_name}.{target})"))
    return out


def _opposite_expand(type_scopes: dict, type_name: str, role_name: str,
                     _stack: tuple, chain: str = "") -> list[dict]:
    """嵌套 role 的对侧展开：找 T 内显式对侧 Y（`Y: invert X` 纯声明）→
    展开 Y（其定义已含方向反转）；找不到 → 递归 invert_role(T.X)。"""
    tsc = type_scopes.get(type_name)
    if tsc is not None:
        for rname, sym in tsc.symbols.items():
            if getattr(sym, "kind", "") != "role" or rname == role_name:
                continue
            rs = _role_raw_ports(type_scopes, type_name, rname)
            if rs is None:
                continue
            if (len(rs) == 1 and rs[0].get("node_name") == "TypeInvertPort"
                    and rs[0].get("target_role", "") == role_name):
                return _expand_role(type_scopes, type_name, rname, _stack,
                                    f"{chain} > via({type_name}.{rname})")
    return _invert_role(type_scopes, type_name, role_name, _stack, chain)


# ── 辅助 ─────────────────────────────────────────────


def _append_ansi(out: list[dict], p: dict, invert: bool = False,
                 chain: str = "") -> None:
    """把一个 Ansi 端口声明项追加到 out（方向可选反转）。

    p: {direction, items:{items:[{name, packed_range?}]}, packed_range?}
    行携带 origin（来源链 + `#端口名`）；chain 空则不加（无溯源要求的调用）。
    """
    d = p.get("direction", "")
    if invert:
        d = _DIR_INV.get(d, d)
    items = (p.get("items") or {}).get("items", [])
    for it in items or []:
        nm = (it.get("name") or "") if isinstance(it, dict) else _text(it)
        if not nm:
            continue
        entry: dict = {"direction": d, "name": nm}
        pr = p.get("packed_range")
        if pr:
            entry["packed_range"] = pr
        if chain:
            entry[ROW_ORIGIN] = f"{chain} > #{nm}"
        out.append(entry)


def _role_raw_ports(type_scopes: dict, type_name: str,
                    role_name: str) -> list[dict] | None:
    """type 内 role 的 raw ports（声明捕获数据）；type/role 不存在返回 None。"""
    tsc = type_scopes.get(type_name)
    if tsc is None:
        return None
    sym = tsc.symbols.get(role_name)
    if sym is None or getattr(sym, "kind", "") != "role":
        return None
    ports = sym.attrs.get("ports", [])
    return ports if isinstance(ports, list) else [ports] if ports else []


def _collect_type_scopes(root) -> dict:
    """DFS scope 树，收集 kind=type 的作用域 {类型名: Scope}。"""
    out: dict = {}

    def _walk(sc):
        for child in getattr(sc, "children", []) or []:
            if getattr(child, "kind", "") == "type":
                out[child.name] = child
            _walk(child)

    _walk(root)
    return out


def _text(node) -> str:
    """Node → 文本（防御非 Node；穿透取首个 content）。"""
    if not isinstance(node, Node):
        return str(node) if node else ""
    content = getattr(node, "content", "") or ""
    if content:
        return content
    for child in node.iter_children():
        t = _text(child)
        if t:
            return t
    return ""
