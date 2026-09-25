"""feature_sites.py — 功能散点计量（"一处功能、N 处登记"的接触点清单）。

**度量什么**：把"加一个功能要碰哪些地方"变成可复现的数字——按**功能分族**枚举现存
实例，对每个实例扫出**提及它的文件**（= 该功能的登记点集合），按角色归类：

    插件内     实现与声明面（tpc.toml / 实现 .py / rules/*.toml）
    引擎侧登记 引擎/工具里必须跟着改的白名单、契约键、词汇表
    行为基线   expected.json / diag_baseline.json / min_pack_baseline.json / 变异注入器
    测试       测试文件（应该多，不计入"欠账"）
    文档       README / docs / CHANGELOG（应该多，不计入"欠账"）

**判据不是"文件多"**——测试与文档本来就该有。判的是**同一事实被写在 ≥2 个必须手工
保持同步的位置**：`引擎侧登记` + `行为基线` 两类是"散点"，`插件内`是"实现面"。

**口径与停止规则**：同 `policy/structural_budget.md`——度量的是"**未处置的欠账**"，
逐项下结论（该合并 / 该接受）后记入 `feature_sites_kept.json` 即从预算里出去
（"保持"是结论，不是"没看"）。工具零猜测：所有实例与接触点都由正则/清单**扫出来**。

用法::

    python tools/feature_sites.py list              # 全部族的接触点清单
    python tools/feature_sites.py list --family check
    python tools/feature_sites.py --save            # 写预算基线（需说明原因）
    python tools/feature_sites.py --compare         # 与基线比对，新增/增长 → exit 1

Doc: docs/gaps/gap-feature-scatter.md（缺口现状 + 候选方案 + 拆步）
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tools" / "feature_sites_baseline.json"
KEPT = ROOT / "tools" / "feature_sites_kept.json"
# 已收敛的登记点（判据：**不再靠人手记着同步**——或由单一来源派生，或由门禁校验；
# 每条须 reason + source 指向具体门禁/机制）。收敛点不计入散点欠账。
CONVERGED = ROOT / "tools" / "feature_sites_converged.json"

# 扫面后缀（文本文件；二进制/构建产物不参与）
SUFFIXES = (".py", ".md", ".toml", ".json", ".cfg", ".txt", ".yml", ".yaml")
# 排除目录：构建产物 / 草稿区 / VCS / 工具自身基线（自引用会造假）
EXCLUDE_DIRS = {
    ".git", "dist", "_drafts", "node_modules", "__pycache__", ".venv",
    ".pytest_cache", "build", ".mypy_cache", ".ruff_cache",
}
# ⚠ 路径一律 POSIX（`_iter_files` 产出 POSIX）——初版用 `Path.relative_to` 的
#   原生分隔符，Windows 下反斜杠匹配不上，基线文件**自己被当语料**（自引用），
#   于是 `--save` 后立刻 `--compare` 就报"44 处散点增长"。
EXCLUDE_FILES = {
    BASELINE.relative_to(ROOT).as_posix(),
    KEPT.relative_to(ROOT).as_posix(),
    CONVERGED.relative_to(ROOT).as_posix(),
}

# 角色归类：前缀（相对路径，POSIX 分隔）→ 角色
_ROLE_RULES: tuple[tuple[str, str], ...] = (
    ("grammar/", "插件内"),
    ("analyzer/", "引擎侧登记"),
    ("core/", "引擎侧登记"),
    ("pipeline/", "引擎侧登记"),
    ("linter/", "引擎侧登记"),
    ("lexer/", "引擎侧登记"),
    ("parser/", "引擎侧登记"),
    ("preprocessor/", "引擎侧登记"),
    ("renderer/", "引擎侧登记"),
    ("transform/", "引擎侧登记"),
    ("tools/", "引擎侧登记"),
    ("tests/e2e/samples/", "行为基线"),
    ("tests/e2e/mutation/", "行为基线"),
    ("tests/", "测试"),
)
_ROLE_DOCS = "文档"
# 散点角色（"同一事实写在多处、必须手工同步"的候选）
SCATTER_ROLES = ("引擎侧登记", "行为基线")


def _role(rel: str) -> str:
    """相对路径 → 角色标签。

    ⚠ `tests/` 下要分两类：`test_*.py` / `conftest.py` 是**测试**（本来就该多，
    不计欠账）；其余（`expected.json` / `*baseline*.json` / `run_all_tests.py` /
    `eval_*.py` / `mutation/`）是**登记面与行为基线**——一条规则码被写进这些文件
    才是"散点"（必须手工保持同步）。本工具初版把它们一并算作"测试"，导致
    W105 的散点数被低估到 3（真实是 20 个文件里的大半）。
    """
    for prefix, role in _ROLE_RULES:
        if rel.startswith(prefix):
            if role == "引擎侧登记" and rel.startswith("tools/") and "baseline" in rel:
                return "行为基线"
            if role == "测试":
                name = rel.rsplit("/", 1)[-1]
                if name.startswith("test_") or name == "conftest.py":
                    return "测试"
                return "行为基线"
            return role
    return _ROLE_DOCS


def _iter_files() -> list[str]:
    """全库文本文件（相对 POSIX 路径，稳定排序）。"""
    out: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(p in EXCLUDE_DIRS for p in rel_parts[:-1]):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDE_FILES:
            continue
        out.append(rel)
    return sorted(out)


# ── 各族的实例枚举（全部机械提取，不写死清单） ──────────────

def _instances_check() -> dict[str, str]:
    """族 `check`：诊断码 → 声明它的插件实现文件（码是规则的对外身份）。"""
    out: dict[str, str] = {}
    pat = re.compile(r"""["']([A-Z]{2,4}\d{2,4})["']""")
    for rel in _iter_files():
        if not rel.startswith("grammar/") or "/checks/" not in rel:
            continue
        if not rel.endswith((".py", ".toml")):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for code in pat.findall(text):
            out.setdefault(code, rel)
    return out


def _instances_syntax() -> dict[str, str]:
    """族 `syntax`：语法插件目录 → 它声明的 grammar 文件（一个构造族 = 一个目录）。

    ⚠ 本族的散点**性质不同**：不是"同一事实写在多处"，而是**一个构造跨多个阶段文件**
    （`tpc.toml` 装配 / `_token_ext.toml` 词法 / `NN_*.toml` 语法 / 可能的渲染规则），
    外加"被登记进启用清单"这类**真散点**。故本族用 `inside`（量跨阶段文件数）+
    `mention_pattern`（只在**声明语境**里找登记点，避开目录名裸匹配的噪声——
    初版拿 `sim` 全库裸匹配，总提及 50 全是 "simple/similar" 这类普通词）。
    """
    out: dict[str, str] = {}
    for tpc in sorted(ROOT.glob("grammar/**/plugins/syntax/*/tpc.toml")):
        out[tpc.parent.name] = tpc.relative_to(ROOT).as_posix()
    return out


def _instances_capability() -> dict[str, str]:
    """族 `capability`：能力名 → 声明它的 tpc.toml（引擎能力位上的一项）。"""
    out: dict[str, str] = {}
    for tpc in sorted(ROOT.glob("grammar/**/tpc.toml")):
        try:
            data = tomllib.loads(tpc.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        caps = data.get("capabilities")
        if not isinstance(caps, dict):
            continue
        for name in caps:
            out.setdefault(name, tpc.relative_to(ROOT).as_posix())
    return out


def _instances_config() -> dict[str, str]:
    """族 `config`：配置段键 → 声明它的引擎模块（`declare_cfg` 的登记面）。

    用 **AST** 取调用实参而不是正则：正则会把模块头 docstring 里的**用法示例**
    （`namespace.key`）也当成真实登记点（初版实测就多出这一条假实例）。
    """
    out: dict[str, str] = {}
    for rel in _iter_files():
        if not rel.endswith(".py") or rel.startswith(("tests/", "grammar/", "tools/")):
            continue
        try:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "declare_cfg" or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.setdefault(arg.value, rel)
    return out


FAMILIES: dict[str, dict] = {
    "check": {
        "desc": "加一条检查规则（诊断码是它的对外身份）",
        "instances": _instances_check,
    },
    "syntax": {
        "desc": "加一个语法构造族（一个插件目录）",
        "instances": _instances_syntax,
        # 跨阶段文件（目录内）+ 只在**声明语境**里找目录外的登记点
        "inside": True,
        "mention_pattern": r"^\s*(requires|enabled|plugins)\s*=.*\b{name}\b"
        r"|\bplugins[./]{name}\b",
    },
    "capability": {
        "desc": "加一个引擎能力位（语言包声明 + 引擎契约）",
        "instances": _instances_capability,
    },
    "config": {
        "desc": "加一个配置段键（引擎 declare_cfg 登记面）",
        "instances": _instances_config,
    },
}


# ── 接触点扫描 ──────────────────────────────────────────────

def scan(families: list[str] | None = None) -> dict:
    """扫出各族每个实例的接触点集合（文件 → 角色）。"""
    files = _iter_files()
    corpus = {rel: (ROOT / rel).read_text(encoding="utf-8", errors="replace") for rel in files}
    kept = _load_kept()
    converged_map = _load_converged()
    result: dict[str, dict] = {}
    for fam, spec in FAMILIES.items():
        if families and fam not in families:
            continue
        entries: dict[str, dict] = {}
        for inst, declared_in in spec["instances"]().items():
            if spec.get("inside"):
                # 跨阶段：目录内文件全算（一个构造 = N 个阶段文件）
                prefix = declared_in.rsplit("/", 1)[0] + "/"
                contacts = {
                    rel: "插件内（跨阶段）" for rel in corpus if rel.startswith(prefix)
                }
                mpat = re.compile(spec["mention_pattern"].format(name=re.escape(inst)))
                contacts.update(
                    {
                        rel: _role(rel)
                        for rel, text in corpus.items()
                        if not rel.startswith(prefix) and mpat.search(text)
                    }
                )
            else:
                pat = re.compile(
                    rf"(?<![A-Za-z0-9_]){re.escape(inst)}(?![A-Za-z0-9_])"
                )
                contacts = {
                    rel: _role(rel) for rel, text in corpus.items() if pat.search(text)
                }
            scatter_all = sorted(
                rel for rel, role in contacts.items() if role in SCATTER_ROLES
            )
            converged = [rel for rel in scatter_all if rel in converged_map]
            scatter = [rel for rel in scatter_all if rel not in converged_map]
            roles: dict[str, int] = {}
            for role in contacts.values():
                roles[role] = roles.get(role, 0) + 1
            stage = sorted(
                rel for rel, role in contacts.items() if role.startswith("插件内（")
            )
            entries[inst] = {
                "declared_in": declared_in,
                "total": len(contacts),
                "roles": dict(sorted(roles.items())),
                "scatter": scatter,
                "scatter_count": len(scatter),
                "converged": converged,
                "converged_count": len(converged),
                "stage_files": stage,
                "stage_count": len(stage),
                "kept": kept.get(f"{fam}:{inst}"),
            }
        counts = sorted(e["scatter_count"] for e in entries.values())
        stages = sorted(e["stage_count"] for e in entries.values())
        result[fam] = {
            "desc": spec["desc"],
            "instances": entries,
            "summary": {
                "instances": len(entries),
                "scatter_total": sum(counts),
                "scatter_median": counts[len(counts) // 2] if counts else 0,
                "scatter_max": counts[-1] if counts else 0,
                "converged_total": sum(e["converged_count"] for e in entries.values()),
                "stage_median": stages[len(stages) // 2] if stages else 0,
                "stage_max": stages[-1] if stages else 0,
                "budget": sum(
                    e["scatter_count"] for e in entries.values() if not e["kept"]
                ),
            },
        }
    return result


def _load_kept() -> dict[str, dict]:
    """已判保持的登记（`family:instance` → {reason, source}）。"""
    if not KEPT.exists():
        return {}
    data = json.loads(KEPT.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("kept", {}).items()}


def _load_converged() -> dict[str, dict]:
    """已收敛的登记点（路径 → {reason, source}）——不计入散点欠账。

    判据：**不再靠人手记着同步**（由单一来源派生，或由门禁校验）。没有判据就
    别往里加——否则等于把欠账洗掉（同 `policy/structural_budget.md` R6 的理由）。
    """
    if not CONVERGED.exists():
        return {}
    data = json.loads(CONVERGED.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("converged", {}).items()}


# ── 输出 ────────────────────────────────────────────────────

def cmd_list(result: dict, verbose: bool) -> None:
    for fam, data in result.items():
        s = data["summary"]
        print(f"\n=== 族 {fam}：{data['desc']} ===")
        print(
            f"    实例 {s['instances']}｜散点合计 {s['scatter_total']}"
            f"（已收敛 {s.get('converged_total', 0)}）"
            f"｜中位 {s['scatter_median']}｜最大 {s['scatter_max']}"
            f"｜**预算（未处置欠账）= {s['budget']}**"
        )
        for inst, e in sorted(
            data["instances"].items(), key=lambda kv: -kv[1]["scatter_count"]
        ):
            mark = "  [已判保持]" if e["kept"] else ""
            stage = f"  跨阶段 {e['stage_count']:>2}" if e.get("stage_count") else ""
            print(
                f"    {inst:<12} 散点 {e['scatter_count']:>2}"
                f"  总提及 {e['total']:>3}{stage}{mark}"
            )
            if verbose:
                for rel in e["scatter"]:
                    print(f"        - {rel}")
                for rel in e.get("stage_files", []):
                    print(f"        ~ {rel}")


def cmd_compare(result: dict) -> int:
    if not BASELINE.exists():
        print("[feature-sites] 基线不存在——先 `--save`", file=sys.stderr)
        return 2
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["families"]
    bad = 0
    for fam, data in result.items():
        old = base.get(fam)
        if old is None:
            print(f"  [新族] {fam}")
            bad += 1
            continue
        old_inst, new_inst = old["instances"], data["instances"]
        for inst in sorted(set(new_inst) - set(old_inst)):
            print(f"  [新实例] {fam}:{inst}（散点 {new_inst[inst]['scatter_count']}）")
        for inst in sorted(set(new_inst) & set(old_inst)):
            o, n = old_inst[inst]["scatter_count"], new_inst[inst]["scatter_count"]
            if n > o and not new_inst[inst]["kept"]:
                print(f"  [散点增长] {fam}:{inst} {o} → {n}")
                for rel in set(new_inst[inst]["scatter"]) - set(old_inst[inst]["scatter"]):
                    print(f"        + {rel}")
                bad += 1
        ob, nb = old["summary"]["budget"], data["summary"]["budget"]
        if nb > ob:
            print(f"  [预算增长] {fam}: {ob} → {nb}")
            bad += 1
    if bad:
        print(f"\n[feature-sites] ✗ {bad} 处散点增长（要么合并登记点，要么登记判保持理由）")
        return 1
    print("[feature-sites] ✓ 无散点增长")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="功能散点计量（接触点清单 + 预算）")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "compare"])
    ap.add_argument("--family", action="append", help="只看某族（可多次）")
    ap.add_argument("--verbose", "-v", action="store_true", help="逐条列出散点文件")
    ap.add_argument("--save", action="store_true", help="写基线（覆盖）")
    args = ap.parse_args()

    result = scan(args.family)
    if args.save:
        BASELINE.write_text(
            json.dumps(
                {"recorded": "2026-09-25", "families": result},
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(f"[feature-sites] 已写基线：{BASELINE.relative_to(ROOT)}")
        return 0
    if args.cmd == "compare":
        return cmd_compare(result)
    cmd_list(result, args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
