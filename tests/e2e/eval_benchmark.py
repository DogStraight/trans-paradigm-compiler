"""eval_benchmark.py — 对标测试（试水第四弹）：tpc check vs 多 oracle lint。

同一输入分别跑 tpc 检查链与参考工具（Verilator / Verible / svlint），
按"可比码族"映射表对齐诊断，输出差异分类：

    共识    — tpc 报 & oracle 报（同文件近似同行）
    仅 tpc  — tpc 报、oracle 不报 → FP 候选（需人工查证）
    仅 oracle — oracle 报、tpc 不报 → 漏报候选 / scope 差异
    范围外  — oracle 的码不在可比码族内（性能/风格/仿真类，计数不判定）

输入集（工程分组，oracle 需要完整实例树）：
    real  — tests/e2e/samples/real/ref/（uart 三文件一组，其余单文件）
    acc   — tests/e2e/samples/check_accuracy/cases/（每 case 一个工程）

行对齐：tpc 诊断 line 是 0-based（LSP），oracle 是 1-based → +1；
按 ±2 行容差匹配（诊断常落在声明行 vs 使用行）。

oracle 选择（--oracle 可重复；缺省全部可用项）：
    verilator — 语义最强（位宽/锁存/未使用/多驱动），MSYS2
    verible   — 语法/风格向（case 缺 default/命名/宏卫生），已捆绑
    svlint    — 规则工程化范本（159 条），cargo 安装

用法:
    python tests/e2e/eval_benchmark.py            # 真实语料（全部 oracle）
    python tests/e2e/eval_benchmark.py --acc      # 评测集
    python tests/e2e/eval_benchmark.py --oracle=verible   # 单 oracle
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


# ── Verible lint oracle ─────────────────────────────────────────
# 已捆绑 tests/differential/.tools/verible/verible-verilog-lint.exe。
# 输出格式：file:line:col-col: msg [Style: xxx] [rule-name]（1-based）。
_VERIBLE_BIN = os.path.join(
    "tests", "differential", ".tools", "verible", "verible-verilog-lint.exe"
)
_VERIBLE_RE = re.compile(
    r"^([^:]+):(\d+):(\d+)(?:-\d+)?:\s+(.*?)\s*\[.*\]\s*\[([a-z0-9-]+)\]$"
)
# Verible 规则名 → tpc 规则码（重叠子集；风格向规则不映射 = 范围外）
VERIBLE2T = {
    "case-missing-default": "CC001",
    "always-comb-blocking": "AW002",    # 组合逻辑 NBA
    "always-ff-non-blocking": "AW001",  # 时序逻辑阻塞赋值
    "generate-label": "NC001",          # generate 块未命名（命名族）
    "generate-label-prefix": "NC001",
    "module-filename": "NC001",         # 文件名≠模块名（命名族）
    "one-module-per-file": "NC001",
    "legacy-generate-region": "NC001",
    "legacy-genvar-declaration": "NC001",
    "macro-name-style": "NC001",
    "port-name-suffix": "NC014",        # 端口后缀（对齐 tpc 方向后缀）
    "signal-name-style": "NC001",
    "parameter-name-style": "NC001",
    "parameter-type-name-style": "NC001",
}


def _run_verible(files: list[str]) -> tuple[list[dict], list[str]]:
    """跑 verible-verilog-lint --ruleset=all，返回 (diagnostics, errors)。"""
    if not os.path.exists(_VERIBLE_BIN):
        return [], ["verible 未捆绑"]
    proc = subprocess.run(
        [_VERIBLE_BIN, "--ruleset=all", *files],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    diags, errors = [], []
    for line in out.splitlines():
        m = _VERIBLE_RE.match(line.strip())
        if m:
            fpath, ln, col, msg, rule = m.groups()
            diags.append({
                "code": rule, "file": os.path.basename(fpath),
                "line": int(ln), "col": int(col), "msg": msg.strip(),
            })
            continue
        if line.strip():
            errors.append(line.strip())
    return diags, errors


# ── svlint oracle ───────────────────────────────────────────────
# 预编译二进制（用户提供，E:\research\svlint\release\bin\svlint.exe）。
# 输出 miette 格式：`Fail: rule_name` 块 + `--> file:line:col`（1-based）。
_SVLINT_BIN = r"E:\research\svlint\release\bin\svlint.exe"
_SVLINT_FAIL_RE = re.compile(r"^Fail:\s*([a-z0-9_]+)")
_SVLINT_POS_RE = re.compile(r"^-->\s+([^:]+):(\d+):(\d+)")
# svlint 规则名 → tpc 规则码（重叠子集；命名族宽进，其余按语义精确映射）
SVLINT2T = {
    "explicit_case_default": "CC001",
    "case_default": "CC001",
    "blocking_assignment_in_always_ff": "AW001",
    "non_blocking_assignment_in_always_comb": "AW002",
    "generate_label": "NC001",
    "instance_parameter_interface": "W103",
    "port_name_suffix": "NC014",
    "name_style": "NC001",
    "signal_name_style": "NC001",
    "parameter_name_style": "NC001",
    "width_mismatch": "W201",
    "width_truncation": "W201",
    "inout_with_tri": "W106",
    "unused_signal": "UN001",
    "unused_parameter": "UN001",
    "multi_driven": "W105",
    "missing_port": "W104",
}
# svlint 规则（不映射 tpc，进范围外计数不判定）——语义差异说明：
# explicit_if_else 是风格规则（SV 要求显式 always_* + 完整 if-else，
# 时序 always 也报），tpc LC001 只报组合锁存语义——规则定位不同，
# 不映射（避免把风格差异误判为漏报）。
_SVLINT_SCOPE_OUT = {
    "explicit_if_else",
    "header_copyright",
    "style_indent",
    "module_identifier_matches_filename",
    "default_nettype_none",
    "explicit_parameter_storage_type",
    "explicit_function_task_parameter_type",
}


def _run_svlint(files: list[str]) -> tuple[list[dict], list[str]]:
    """跑 svlint，返回 (diagnostics, errors)。

    miette 输出（ANSI 彩色）：`Fail: rule_name` 后跟 `--> file:line:col`
    定位块 + `|` 代码框 + hint/reason。先 strip ANSI 转义再解析。
    规则名不在 SVLINT2T 的（风格/版权/命名规则）→ 范围外，由 _classify
    的 scope_out 处理。
    """
    if not os.path.exists(_SVLINT_BIN):
        return [], ["svlint 未找到: %s" % _SVLINT_BIN]
    proc = subprocess.run(
        [_SVLINT_BIN, *files],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # 去 ANSI 颜色码（\x1b[...m）
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    diags, errors = [], []
    cur_rule = None
    for line in out.splitlines():
        m = _SVLINT_FAIL_RE.match(line.strip())
        if m:
            cur_rule = m.group(1)
            continue
        p = _SVLINT_POS_RE.match(line.strip())
        if p and cur_rule:
            fpath, ln, col = p.groups()
            diags.append({
                "code": cur_rule, "file": os.path.basename(fpath),
                "line": int(ln), "col": int(col), "msg": "",
            })
            cur_rule = None
            continue
        # miette 代码框（| / ^ / =）、hint/reason、空行 → 忽略；
        # Warning（无 config）→ 忽略；其余（真错误）→ errors
        s = line.strip()
        if not s or s.startswith(("|", "^", "=", "hint", "reason", "Warning",
                                  "note", "error", "Error")):
            continue
        errors.append(s)
    return diags, errors


# ── slang oracle ────────────────────────────────────────────────
# slang v11.0（用户下载 E:\research\slang\slang.exe，源码 E:\research\
# slang-11.0）。--lint-only + 显式 -W 开启警告；--diag-json 输出
# [{severity, message, optionName, location: "file:line:col", ...}]。
# 警告名全集见 scripts/diagnostics.txt（width-trunc/port-width-trunc/
# inferred-latch/case-incomplete/index-oob/unused-* 族）。
_SLANG_BIN = r"E:\research\slang\slang.exe"
# slang 警告名 → tpc 规则码（重叠子集；语义精确映射）
SLANG2T = {
    "width-trunc": "W201",          # 隐式转换截断
    "port-width-trunc": "W201",     # 端口连接截断
    "port-width-expand": "W201",    # 端口连接扩展（tpc 只报截断）
    "index-oob": "W202",            # 位选越界
    "range-oob": "W202",            # 范围越界
    "range-width-oob": "W202",
    "inferred-latch": "LC001",      # 锁存
    "case-incomplete": "CC001",     # case 未全覆盖
    "case-none": "CC001",           # case 无匹配无 default
    "unused-net": "UN001",          # 未使用 net
    "unused-variable": "UN001",     # 未使用变量
    "unused-parameter": "UN001",    # 未使用参数
    "unused-port": "UN001",
    "unused-but-set-port": "UN001",
    "unused-but-set-variable": "UN001",
    "unused-typedef": "UN001",
    "unused-genvar": "UN001",
}
# 开启的警告（-W 逐个；对应 tpc 语义面的子集）
_SLANG_WARNS = [
    "width-trunc", "port-width-trunc", "port-width-expand",
    "index-oob", "range-oob", "range-width-oob",
    "inferred-latch", "case-incomplete", "case-none",
    "unused-net", "unused-variable", "unused-parameter",
    "unused-port", "unused-but-set-port", "unused-but-set-variable",
    "unused-typedef", "unused-genvar",
]
_SLANG_JSON_RE = re.compile(
    r'"location":\s*"([^"]+)"'
)


def _run_slang(files: list[str]) -> tuple[list[dict], list[str]]:
    """跑 slang --lint-only，返回 (diagnostics, errors)。

    --diag-json - 输出 JSON 数组到 stdout（{severity, message,
    optionName, location: "file:line:col"}）。location 是 1-based 行/列。
    """
    if not os.path.exists(_SLANG_BIN):
        return [], ["slang 未找到: %s" % _SLANG_BIN]
    args = [_SLANG_BIN, "--std=1364-2005", "--lint-only", "--diag-json", "-"]
    for w in _SLANG_WARNS:
        args.append("-W" + w)
    args.extend(files)
    proc = subprocess.run(
        args, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    diags, errors = [], []
    # 从合并输出提取 JSON 数组段（stdout 的 [ ... ]）
    import json as _json
    start = out.find("[")
    end = out.rfind("]")
    arr = []
    if start != -1 and end > start:
        try:
            arr = _json.loads(out[start:end + 1])
        except Exception:
            errors.append("JSON parse fail: %s" % out[start:start + 200])
    for item in arr:
        if not isinstance(item, dict):
            continue
        oname = item.get("optionName", "")
        loc = item.get("location", "") or ""
        m = re.match(r"^(.+):(\d+):(\d+)$", loc)
        if not m:
            errors.append("location parse fail: %s" % loc)
            continue
        fpath, ln, col = m.groups()
        diags.append({
            "code": oname, "file": os.path.basename(fpath),
            "line": int(ln), "col": int(col),
            "msg": item.get("message", ""),
        })
    for line in out.splitlines():
        if "Build succeeded" in line or "Build failed" in line:
            continue
        s = line.strip()
        if not s:
            continue
        # JSON 数组段内的行（[{},:] 等）不算错误
        if s in ("[", "]", "{", "}", "},", "{", "],"):
            continue
        if s.startswith(('"', "{")) and s.endswith((",", "")):
            continue
        if "symbolPath" in s or '"optionName"' in s or '"location"' in s \
                or '"message"' in s or '"severity"' in s:
            continue
        errors.append(s)
    return diags, errors


# oracle 注册表：name → (run 函数, 码映射表, 范围外码集)
_ORACLES = {
    "verilator": (_run_verilator, W2T, _SCOPE_OUT),
    "verible": (_run_verible, VERIBLE2T, set()),
    "svlint": (_run_svlint, SVLINT2T, _SVLINT_SCOPE_OUT),
    "slang": (_run_slang, SLANG2T, set()),
}


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


def _tpc_diags_all(checker, files: list[str]) -> tuple[list[dict], bool]:
    """跑 tpc check 覆盖文件组**全部**文件（oracle 扫全目录对齐）。

    与 _tpc_diags 的差异：oracle（Verible/svlint/slang）对每个输入文件
    独立扫，而 tpc 从 entry 递归只能发现 entry 依赖链上的模块——多文件
    工程里 entry 不依赖的独立文件（如 project_bus_ctrl 的 reg_if 不被
    arbiter 依赖）tpc 会漏扫。

    实现：对 entry 跑**一次** check（全量编译覆盖依赖链），再对 entry
    未覆盖的独立文件补 check（避免对每文件重复全量编译——picorv32 单次
    check ~95s，N 文件 × N 次会数分钟超时）。
    """
    out: list[dict] = []
    parse_ok = True
    seen: set[tuple] = set()
    # entry = 文件组第一个文件；一次 check 覆盖其依赖链
    entry = files[0]
    report = checker.check(entry)
    covered_paths = {os.path.abspath(f["path"]) for f in report.get("files", [])}
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
            key = (code, base, line0 + 1)
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": code, "file": base, "line": line0 + 1})
    # 补查 entry 未覆盖的独立文件（不在依赖链的）
    for path in files:
        if os.path.abspath(path) in covered_paths:
            continue
        r2 = checker.check(path)
        for f in r2.get("files", []):
            if not f.get("parse_ok") or f.get("syntax"):
                parse_ok = False
                continue
            base = os.path.basename(f["path"])
            for d in f.get("semantic", []):
                code = d.get("code")
                if not code:
                    continue
                line0 = (d.get("range") or {}).get("start", {}).get("line", 0)
                key = (code, base, line0 + 1)
                if key in seen:
                    continue
                seen.add(key)
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


def _classify(tpc_diags, ow: list[dict], lint_offs: dict[str, set] | None = None,
              has_cond: bool = False, w2t: dict | None = None,
              scope_out: set | None = None) -> dict:
    """按可比码族对齐两侧诊断（tpc vs 单个 oracle），返回差异分类。

    w2t: oracle 码 → tpc 码映射表（缺省 W2T）；scope_out: oracle 范围外
    码集（缺省 _SCOPE_OUT）——只计数不判定。

    lint_offs: {file: 被抑制的 tpc 码集}——被抑制的 tpc 诊断不进
    "仅 tpc（FP 候选）"（oracle 不报是源码 lint_off 主动关闭，
    不是判断差异），单独计为"抑制（作者主动关）"。

    has_cond: 文件含条件编译（ifdef 等）→ 展开后行号 ≠ 源行号
    （P3.3），按行对齐不可靠：改为**同文件同码族按数量对齐**
    （共识 = 两侧数量一致；仅一侧多出 = 对应候选）。
    """
    w2t = w2t or W2T
    scope_out = scope_out if scope_out is not None else _SCOPE_OUT
    lint_offs = lint_offs or {}
    tpc_by_code: dict[str, list[dict]] = {}
    for d in tpc_diags:
        tpc_by_code.setdefault(d["code"], []).append(d)
    v_by_tpc: dict[str, list[dict]] = {}   # tpc 码 -> oracle diagnostics（映射后）
    v_scope_out: list[dict] = []
    for w in ow:
        if w["code"] in scope_out:
            v_scope_out.append(w)
            continue
        tcode = w2t.get(w["code"])
        if tcode:
            v_by_tpc.setdefault(tcode, []).append(w)

    consensus, only_tpc, only_v, suppressed = [], [], [], []
    # 共识 / 仅 tpc：对每个 tpc 诊断找 oracle 对应
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
                    consensus.append({"tpc": d, "oracle": vlist[i]})
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
                    consensus.append({"tpc": d, "oracle": hit})
                elif code in lint_offs.get(d["file"], set()):
                    # 源码 lint_off 主动关闭该族 → 作者明确不想要，非 FP 候选
                    suppressed.append(d)
                else:
                    only_tpc.append(d)
    # 仅 oracle：未匹配的（含扩展侧单独归一类）
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


def run(checker, groups, label: str,
        oracles: list[str] | None = None) -> tuple[list[dict], dict]:
    """对每个工程跑 tpc + 选定 oracle(s)，返回 (rows, summary)。

    oracles: 选定的 oracle 名列表（缺省全部可用项）。每 oracle 独立
    classify（共识/仅 tpc/仅 oracle），rows 每工程每 oracle 一行。
    """
    oracles = oracles or list(_ORACLES.keys())
    rows = []
    stats = {
        "groups": 0, "oracle_skip": 0, "tpc_parse_fail": 0,
        "consensus": 0, "only_tpc": 0, "only_v": 0, "suppressed": 0,
        "v_scope_out": 0, "v_expand": 0,
        "per_oracle": {o: {"consensus": 0, "only_tpc": 0, "only_v": 0,
                           "suppressed": 0, "scope_out": 0}
                       for o in oracles},
    }
    for g in groups:
        stats["groups"] += 1
        entry = g.get("entry", g["files"][0])
        # tpc 检查覆盖文件组全部文件（oracle 扫全目录对齐；entry 递归
        # 会漏扫 entry 不依赖的独立文件）
        tpc, tpc_parse_ok = _tpc_diags_all(checker, g["files"])
        if not tpc_parse_ok:
            # tpc 解析失败（如 darkriscv 条件编译嵌套位置，P1.5）→
            # 0 诊断是"假干净"，不能当 MISS/共识，标为无法对拍
            stats["tpc_parse_fail"] += 1
            rows.append({"name": g["name"], "verdict": "TPC-PARSE-FAIL"})
            continue
        lint_offs = _file_lint_offs(g["files"])
        has_cond = _file_has_cond(g["files"])
        for oname in oracles:
            run_fn, w2t, scope_out = _ORACLES[oname]
            ow, oerr = run_fn(g["files"])
            if oerr and not ow:
                # oracle 硬错误（MODMISSING 缺子模块/未安装）→ 无法对拍
                stats["oracle_skip"] += 1
                rows.append({"name": g["name"], "oracle": oname,
                             "verdict": "ORACLE-SKIP", "o_errors": oerr})
                continue
            if not tpc and not ow:
                rows.append({"name": g["name"], "oracle": oname,
                             "verdict": "CLEAN-BOTH"})
                continue
            cls = _classify(tpc, ow, lint_offs, has_cond, w2t, scope_out)
            cls["o_errors"] = oerr
            verdict = "OK"
            if cls["only_tpc"]:
                verdict = "FP-CANDIDATE"
            elif cls["only_v"]:
                verdict = "MISS-CANDIDATE"
            po = stats["per_oracle"][oname]
            po["consensus"] += len(cls["consensus"])
            po["only_tpc"] += len(cls["only_tpc"])
            po["only_v"] += len(cls["only_v"])
            po["suppressed"] += len(cls["suppressed"])
            po["scope_out"] += len(cls["v_scope_out"])
            stats["consensus"] += len(cls["consensus"])
            stats["only_tpc"] += len(cls["only_tpc"])
            stats["only_v"] += len(cls["only_v"])
            stats["suppressed"] += len(cls["suppressed"])
            stats["v_scope_out"] += len(cls["v_scope_out"])
            stats["v_expand"] += len(cls["v_expand"])
            rows.append({"name": g["name"], "oracle": oname,
                         "verdict": verdict, "tpc": tpc,
                         "oracle_diags": ow, **cls})
    summary = {
        "输入工程数": stats["groups"],
        "oracle 跳过（硬错误/未安装）": stats["oracle_skip"],
        "tpc 解析失败": stats["tpc_parse_fail"],
        "共识（双方同报）": stats["consensus"],
        "仅 tpc（FP 候选）": stats["only_tpc"],
        "仅 oracle（漏报/scope 候选）": stats["only_v"],
        "tpc 被源码 lint_off 抑制": stats["suppressed"],
        "oracle 范围外码（计数不判定）": stats["v_scope_out"],
        "oracle 扩展侧 WIDTHEXPAND": stats["v_expand"],
        "groups": stats["groups"],
        "oracle_skip": stats["oracle_skip"],
        "consensus": stats["consensus"],
        "only_tpc": stats["only_tpc"],
        "only_v": stats["only_v"],
        "suppressed": stats["suppressed"],
        "v_scope_out": stats["v_scope_out"],
        "v_expand": stats["v_expand"],
        "per_oracle": stats["per_oracle"],
    }
    return rows, summary


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    os.chdir(_ROOT)
    checker = ProjectChecker(rules_dir="grammar/verilog")
    use_acc = "--acc" in sys.argv
    # --oracle=name 可重复；缺省全部注册 oracle
    oracles = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--oracle=")]
    if not oracles:
        oracles = list(_ORACLES.keys())
    groups = _acc_groups() if use_acc else [
        {**g, "files": [os.path.join(_REAL_DIR, f) for f in g["files"]],
         "entry": os.path.join(_REAL_DIR, g["files"][0])}
        for g in _GROUPS
    ]
    rows, summary = run(checker, groups, "acc" if use_acc else "real",
                        oracles=oracles)

    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "summary": summary},
                         ensure_ascii=False, indent=2))
        return

    oracle_label = "+".join(oracles)
    print("=" * 100)
    print(f"对标测试：tpc check vs {oracle_label} "
          f"({'评测集' if use_acc else '真实语料'})")
    print("=" * 100)
    for r in rows:
        tag = r.get("verdict", "")
        extra = ""
        if "consensus" in r:
            extra = (f"共识={len(r['consensus'])} 仅tpc={len(r['only_tpc'])} "
                     f"仅{oracle_label}={len(r['only_v'])} "
                     f"抑制={len(r['suppressed'])} 范围外={len(r['v_scope_out'])}")
        name = r["name"]
        if r.get("oracle"):
            name = f"{r['name']}[{r['oracle']}]"
        print(f"{name:<30}{tag:<16}{extra}")
    print("=" * 100)
    for k, v in summary.items():
        if k == "per_oracle":
            for o, po in v.items():
                print(f"  {o:<12}共识={po['consensus']} 仅tpc={po['only_tpc']} "
                      f"仅o={po['only_v']} 抑制={po['suppressed']} "
                      f"范围外={po['scope_out']}")
            continue
        print(f"{k:<36}{v}")

    # 差异明细（仅 tpc / 仅 oracle）
    print("\n── 仅 tpc 报（FP 候选）──")
    for r in rows:
        for d in r.get("only_tpc", []):
            o = f"[{r['oracle']}]" if r.get("oracle") else ""
            print(f"  {r['name']}{o:<30}{d['code']:<8}{d['file']}:{d['line']}")
    print(f"\n── 仅 oracle 报（漏报/scope 候选）──")
    for r in rows:
        for w in r.get("only_v", []):
            o = f"[{r['oracle']}]" if r.get("oracle") else ""
            print(f"  {r['name']}{o:<30}{w['code']:<20}{w['file']}:{w['line']} {w['msg'][:50]}")


if __name__ == "__main__":
    main()
