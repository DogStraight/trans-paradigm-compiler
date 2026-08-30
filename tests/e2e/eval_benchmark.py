"""eval_benchmark.py — 对标测试（试水第四弹）：tpc check vs Verilator lint。

同一输入分别跑 tpc 检查链与 Verilator --lint-only -Wall，按"可比码族"
映射表对齐诊断，输出差异分类：

    共识    — tpc 报 & Verilator 报（同文件近似同行）
    仅 tpc  — tpc 报、Verilator 不报 → FP 候选（需人工查证）
    仅 Verilator — Verilator 报、tpc 不报 → 漏报候选 / scope 差异
    范围外  — Verilator 的 W 码不在可比码族内（性能/风格/仿真类，
              计数但不参与对拍判定——落档说明，不混入结论）

输入集（工程分组，Verilator 需要完整实例树）：
    real  — tests/e2e/samples/real/ref/（uart 三文件一组，其余单文件）
    acc   — tests/e2e/samples/check_accuracy/cases/（每 case 一个工程）

行对齐：tpc 诊断 line 是 0-based（LSP），Verilator 是 1-based → +1；
按 ±2 行容差匹配（诊断常落在声明行 vs 使用行）。

用法:
    python tests/e2e/eval_benchmark.py            # 真实语料
    python tests/e2e/eval_benchmark.py --acc      # 评测集
    python tests/e2e/eval_benchmark.py --json     # 完整 JSON
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from analyzer.checker import ProjectChecker

_BASH = r"C:\msys64\usr\bin\bash.exe"
_REAL_DIR = os.path.join("tests", "e2e", "samples", "real", "ref")
_ACC_DIR = os.path.join("tests", "e2e", "samples", "check_accuracy", "cases")

# ── 可比码族：Verilator W 码 ↔ tpc 规则码（对拍判定只看这个集合）──
# 选入标准：两工具都有语义对应的码（位宽/锁存/未使用/多驱动/未连接/
# 阻塞时序/组合 NBA）。Verilator 范围外码（DECLFILENAME/MULTITOP/
# GENUNNAMED/COMBDLY? 等）在 _SCOPE_OUT 里，只计数不判定。
W2T = {
    "WIDTHTRUNC": "W201",   # 赋值/端口截断（含条件测试宽度——scope 差异在结论里量化）
    "WIDTHEXPAND": "W201",  # 扩展侧（tpc 只报截断；Verilator 双向）
    "SELRANGE": "W202",     # 位选越界
    "LATCH": "LC001",       # 组合 always 锁存
    "UNUSEDSIGNAL": "UN001",  # 未使用信号（tpc 按符号整报，Verilator 可按位）
    "UNUSEDPARAM": "UN001",   # 未使用参数
    "MULTIDRIVEN": "W105",    # 多驱动
    "PINMISSING": "W104",     # 端口缺连
    "PINNOCONNECT": "W104",   # 端口空连
    "BLKSEQ": "AW001",        # 时序块阻塞赋值
    "COMBDLY": "AW002",       # 组合块 NBA
}
_SCOPE_OUT = {
    "DECLFILENAME", "MULTITOP", "GENUNNAMED", "PROCASSINIT",
    "UNDRIVEN", "UNOPTFLAT", "UNOPTIMIZED", "TIMESCALEMOD",
    "IMPLICIT", "WIDTHCONCAT", "WIDTHEXPAND",
}
# Verilator lint 指令抑制的码 → 其对应 tpc 码（源码 lint_off 意味着作者
# 主动关掉该族检查——Verilator 不报是被抑制，不是"判断一致"。对拍判定
# 中"仅 Verilator 不报"必须排除被抑制族，否则会把抑制误判为漏报。
# 2026-08-29 实测：picorv32 源码第 20-23 行 lint_off WIDTH/PINMISSING/
# CASEOVERLAP/CASEINCOMPLETE——tpc 的 8 条 W201 与 Verilator 默认判断
# 一致（若未抑制 Verilator 会报 WIDTHTRUNC），落档结论不推翻。
_LINT_OFF2TPC = {
    "WIDTH": {"W201", "W202"},          # lint_off WIDTH 覆盖 WIDTHTRUNC/WIDTHEXPAND/SELRANGE
    "WIDTHTRUNC": {"W201"},
    "WIDTHEXPAND": {"W201"},
    "SELRANGE": {"W202"},
    "PINMISSING": {"W104"},
    "PINNOCONNECT": {"W104"},
    "CASEINCOMPLETE": {"CC001"},
    "CASEOVERLAP": {"CC001"},
    "LATCH": {"LC001"},
    "MULTIDRIVEN": {"W105"},
    "UNUSED": {"UN001"},
    "UNUSEDSIGNAL": {"UN001"},
    "UNUSEDPARAM": {"UN001"},
    "BLKSEQ": {"AW001"},
    "COMBDLY": {"AW002"},
}
# 源码级 lint_off 指令（/* verilator lint_off CODE */）
_LINT_OFF_RE = re.compile(r"verilator\s+lint_off\s+([A-Z0-9_]+)")
# WIDTHEXPAND 双向：tpc 只报截断不报扩展——WIDTHEXPAND 单独计为"扩展侧差异"
_EXPAND_ONLY = {"WIDTHEXPAND"}
_WARN_RE = re.compile(
    r"%Warning-([A-Z0-9_]+):\s+(\S+):(\d+):(\d+):\s+(.*)"
)
_ERR_RE = re.compile(r"%Error(?:-([A-Z0-9_]+))?:\s+")

# 工程分组：多文件工程（Verilator 一次喂全部；tpc 从 entry 递归发现）
_GROUPS: list[dict] = [
    {"name": "real_uart", "files": ["ref_uart.v", "ref_uart_rx.v", "ref_uart_tx.v"]},
    {"name": "real_darkriscv", "files": ["ref_darkriscv.v"]},
    {"name": "real_ice40_cells_sim", "files": ["ref_ice40_cells_sim.v"]},
    {"name": "real_picorv32", "files": ["ref_picorv32.v"]},
    {"name": "real_serv_top", "files": ["ref_serv_top.v"]},
    {"name": "real_simcells", "files": ["ref_simcells.v"]},
    {"name": "real_tv80_core", "files": ["ref_tv80_core.v"]},
]


def _msys_path(win_path: str) -> str:
    """E:\\project\\... → /e/project/...（MSYS bash 可消费）。"""
    drive, rest = os.path.splitdrive(os.path.abspath(win_path))
    drive = drive.rstrip(":").lower()
    return "/" + drive + rest.replace("\\", "/")


def _run_verilator(files: list[str]) -> tuple[list[dict], list[str]]:
    """跑 verilator --lint-only -Wall，返回 (warnings, errors)。

    warning = {code, file, line(1-based), msg}；文件路径保持相对项目根。
    MSYS2 的 verilator 是 perl 包装脚本，须在非 login bash 下跑（-lc 的
    login shell 环境会导致 ulimit/exec 失败）——用临时 .sh 脚本承载。
    """
    script = (
        "export PATH=/mingw64/bin:/usr/bin:$PATH\n"
        f"cd {_msys_path(_ROOT)}\n"
        "verilator --lint-only -Wall "
        + " ".join(_msys_path(f) for f in files)
        + "\n"
    )
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(script)
        tmp.close()
        proc = subprocess.run(
            [_BASH, tmp.name], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    finally:
        os.unlink(tmp.name)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    warnings, errors = [], []
    for line in out.splitlines():
        m = _WARN_RE.match(line.strip())
        if m:
            code, fpath, ln, col, msg = m.groups()
            warnings.append({
                "code": code, "file": os.path.basename(fpath),
                "line": int(ln), "col": int(col), "msg": msg.strip(),
            })
            continue
        e = _ERR_RE.match(line.strip())
        if e:
            errors.append(line.strip())
    return warnings, errors


def _tpc_diags(checker, entry: str) -> tuple[list[dict], bool]:
    """跑 tpc check，返回 (诊断列表, parse_ok)。"""
    report = checker.check(entry)
    out = []
    parse_ok = True
    for f in report.get("files", []):
        if not f.get("parse_ok") or f.get("syntax"):
            parse_ok = False
            continue
        base = os.path.basename(f["path"])
        for d in f.get("semantic", []):
            code = d.get("code")
            if not code:
                continue
            line0 = (d.get("range") or {}).get("start", {}).get("line", 0)
            out.append({"code": code, "file": base, "line": line0 + 1})
    return out, parse_ok


def _near(a: dict, b: dict, tol: int = 2) -> bool:
    """同文件同码族、行距 ≤ tol 视为对齐。"""
    return a["file"] == b["file"] and abs(a["line"] - b["line"]) <= tol


def _file_lint_offs(files: list[str]) -> dict[str, set]:
    """每个文件源码级 verilator lint_off 码族 → 对应 tpc 码集。

    key = basename；值 = 被抑制的 tpc 码（通过 _LINT_OFF2TPC 映射，
    未映射的 lint_off 码族忽略）。
    """
    out: dict[str, set] = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        tpc_codes: set[str] = set()
        for m in _LINT_OFF_RE.finditer(src):
            tpc_codes |= _LINT_OFF2TPC.get(m.group(1), set())
        out[os.path.basename(f)] = tpc_codes
    return out


# 条件编译指令（ifdef/ifndef/else/elsif/endif）——展开后 token 行号与
# 源行号偏移（P3.3 已知坑：语义诊断行号在展开后 token 流上，未映射回
# 源文本）。含条件编译的文件按码族数量对齐（行号不可比），否则按行对齐。
_COND_RE = re.compile(r"`(ifdef|ifndef|else|elsif|endif)\b")


def _file_has_cond(files: list[str]) -> bool:
    """文件组任一文件含条件编译指令。"""
    for f in files:
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        if _COND_RE.search(src):
            return True
    return False


def _classify(tpc_diags, vw: list[dict], lint_offs: dict[str, set] | None = None,
              has_cond: bool = False) -> dict:
    """按可比码族对齐两侧诊断，返回差异分类。

    lint_offs: {file: 被抑制的 tpc 码集}——被抑制的 tpc 诊断不进
    "仅 tpc（FP 候选）"（Verilator 不报是源码 lint_off 主动关闭，
    不是判断差异），单独计为"抑制（作者主动关）"。

    has_cond: 文件含条件编译（ifdef 等）→ 展开后行号 ≠ 源行号
    （P3.3），按行对齐不可靠：改为**同文件同码族按数量对齐**
    （共识 = 两侧数量一致；仅一侧多出 = 对应候选）。
    """
    lint_offs = lint_offs or {}
    tpc_by_code: dict[str, list[dict]] = {}
    for d in tpc_diags:
        tpc_by_code.setdefault(d["code"], []).append(d)
    v_by_tpc: dict[str, list[dict]] = {}   # tpc 码 -> verilator warnings（映射后）
    v_scope_out: list[dict] = []
    for w in vw:
        if w["code"] in _SCOPE_OUT:
            v_scope_out.append(w)
            continue
        tcode = W2T.get(w["code"])
        if tcode:
            v_by_tpc.setdefault(tcode, []).append(w)

    consensus, only_tpc, only_v, suppressed = [], [], [], []
    # 共识 / 仅 tpc：对每个 tpc 诊断找 Verilator 对应
    matched_v = set()
    if has_cond:
        # 条件编译文件：行号不可比（展开后 vs 源，P3.3）——按码族数量对齐：
        # 同码族两侧数量一致 → 全部共识；数量差 → 多出侧为候选
        # （码族级判定，不逐条匹配位置）。
        for code, diags in tpc_by_code.items():
            vlist = v_by_tpc.get(code, [])
            for i, d in enumerate(diags):
                if i < len(vlist):
                    matched_v.add(i)
                    consensus.append({"tpc": d, "verilator": vlist[i]})
                elif code in lint_offs.get(d["file"], set()):
                    suppressed.append(d)
                else:
                    only_tpc.append(d)
    else:
        for code, diags in tpc_by_code.items():
            vlist = v_by_tpc.get(code, [])
            for d in diags:
                hit = next((w for i, w in enumerate(vlist)
                            if i not in matched_v and _near(d, w)), None)
                if hit is not None:
                    matched_v.add(vlist.index(hit))
                    consensus.append({"tpc": d, "verilator": hit})
                elif code in lint_offs.get(d["file"], set()):
                    # 源码 lint_off 主动关闭该族 → 作者明确不想要，非 FP 候选
                    suppressed.append(d)
                else:
                    only_tpc.append(d)
    # 仅 Verilator：未匹配的（含扩展侧单独归一类）
    v_unmatched = [
        w for i, (code, w) in enumerate(
            (c, w) for c, ws in v_by_tpc.items() for w in ws
        ) if i not in matched_v
    ]
    for w in v_unmatched:
        if w["code"] in _EXPAND_ONLY:
            continue  # 扩展侧差异进 summary 计数，不逐条列
        only_v.append(w)
    return {
        "consensus": consensus,
        "only_tpc": only_tpc,
        "only_v": only_v,
        "suppressed": suppressed,
        "v_scope_out": v_scope_out,
        "v_expand": [w for w in v_unmatched if w["code"] in _EXPAND_ONLY],
        "v_errors": [],
    }


def _acc_groups() -> list[dict]:
    """评测集 case → 工程组（目录下全部 .sv 一起喂 Verilator）。

    entry：有 top.sv 用 top.sv（多数 case），否则用目录首个 .sv
    （project_bus_ctrl 的 entry 是 bus_ctrl.sv）。
    """
    groups = []
    for name in sorted(os.listdir(_ACC_DIR)):
        d = os.path.join(_ACC_DIR, name)
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d) if f.endswith(".sv"))
        if not files:
            continue
        entry = os.path.join(d, "top.sv") if "top.sv" in files \
            else os.path.join(d, files[0])
        groups.append({
            "name": f"acc_{name}",
            "files": [os.path.join(_ACC_DIR, name, f) for f in files],
            "entry": entry,
        })
    return groups


def run(checker, groups, label: str) -> tuple[list[dict], dict]:
    rows = []
    stats = {
        "groups": 0, "verilator_skip": 0, "tpc_parse_fail": 0,
        "consensus": 0, "only_tpc": 0, "only_v": 0, "suppressed": 0,
        "v_scope_out": 0, "v_expand": 0,
    }
    for g in groups:
        stats["groups"] += 1
        vw, verr = _run_verilator(g["files"])
        if verr and not vw:
            # Verilator 硬错误（如 MODMISSING 缺子模块）→ 无法对拍，跳过
            stats["verilator_skip"] += 1
            rows.append({"name": g["name"], "verdict": "VERILATOR-SKIP",
                         "v_errors": verr})
            continue
        entry = g.get("entry", g["files"][0])
        tpc, tpc_parse_ok = _tpc_diags(checker, entry)
        if not tpc and not vw and tpc_parse_ok:
            rows.append({"name": g["name"], "verdict": "CLEAN-BOTH"})
            continue
        if not tpc_parse_ok:
            # tpc 解析失败（如 darkriscv 条件编译嵌套位置，P1.5）→
            # 0 诊断是"假干净"，不能当 MISS/共识，标为无法对拍
            stats["tpc_parse_fail"] += 1
            rows.append({"name": g["name"], "verdict": "TPC-PARSE-FAIL",
                         "v": vw})
            continue
        lint_offs = _file_lint_offs(g["files"])
        has_cond = _file_has_cond(g["files"])
        cls = _classify(tpc, vw, lint_offs, has_cond)
        cls["v_errors"] = verr
        verdict = "OK"
        if cls["only_tpc"]:
            verdict = "FP-CANDIDATE"
        elif cls["only_v"]:
            verdict = "MISS-CANDIDATE"
        stats["consensus"] += len(cls["consensus"])
        stats["only_tpc"] += len(cls["only_tpc"])
        stats["only_v"] += len(cls["only_v"])
        stats["suppressed"] += len(cls["suppressed"])
        stats["v_scope_out"] += len(cls["v_scope_out"])
        stats["v_expand"] += len(cls["v_expand"])
        rows.append({"name": g["name"], "verdict": verdict,
                     "tpc": tpc, "v": vw, **cls})
    summary = {
        "输入工程数": stats["groups"],
        "Verilator 跳过（硬错误）": stats["verilator_skip"],
        "共识（双方同报）": stats["consensus"],
        "仅 tpc（FP 候选）": stats["only_tpc"],
        "仅 Verilator（漏报/scope 候选）": stats["only_v"],
        "tpc 被源码 lint_off 抑制": stats["suppressed"],
        "Verilator 范围外码（计数不判定）": stats["v_scope_out"],
        "Verilator 扩展侧 WIDTHEXPAND": stats["v_expand"],
        "groups": stats["groups"],
        "verilator_skip": stats["verilator_skip"],
        "consensus": stats["consensus"],
        "only_tpc": stats["only_tpc"],
        "only_v": stats["only_v"],
        "suppressed": stats["suppressed"],
        "v_scope_out": stats["v_scope_out"],
        "v_expand": stats["v_expand"],
    }
    return rows, summary


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    os.chdir(_ROOT)
    checker = ProjectChecker(rules_dir="grammar/verilog")
    use_acc = "--acc" in sys.argv
    groups = _acc_groups() if use_acc else [
        {**g, "files": [os.path.join(_REAL_DIR, f) for f in g["files"]],
         "entry": os.path.join(_REAL_DIR, g["files"][0])}
        for g in _GROUPS
    ]
    rows, summary = run(checker, groups, "acc" if use_acc else "real")

    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "summary": summary},
                         ensure_ascii=False, indent=2))
        return

    print("=" * 100)
    print(f"对标测试：tpc check vs Verilator ({'评测集' if use_acc else '真实语料'})")
    print("=" * 100)
    for r in rows:
        tag = r.get("verdict", "")
        extra = ""
        if "consensus" in r:
            extra = (f"共识={len(r['consensus'])} 仅tpc={len(r['only_tpc'])} "
                     f"仅V={len(r['only_v'])} 抑制={len(r['suppressed'])} "
                     f"范围外={len(r['v_scope_out'])} 扩展={len(r['v_expand'])}")
        print(f"{r['name']:<24}{tag:<16}{extra}")
    print("=" * 100)
    for k, v in summary.items():
        print(f"{k:<36}{v}")

    # 差异明细（仅 tpc / 仅 Verilator）
    print("\n── 仅 tpc 报（FP 候选）──")
    for r in rows:
        for d in r.get("only_tpc", []):
            print(f"  {r['name']:<24}{d['code']:<8}{d['file']}:{d['line']}")
    print("\n── 仅 Verilator 报（漏报/scope 候选）──")
    for r in rows:
        for w in r.get("only_v", []):
            print(f"  {r['name']:<24}{w['code']:<14}{w['file']}:{w['line']} {w['msg'][:60]}")


if __name__ == "__main__":
    main()
