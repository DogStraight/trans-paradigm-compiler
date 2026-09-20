"""structural_score.py — 结构欠账分（把外部裁判的"无穷建议"折成一个标量）

用途：判断"这次改动值不值得做"与"主线何时收口"。外部裁判（Bifrost）按阈值报命中，
修掉一批就会露出下一批（阈值附近的项无穷无尽）；本工具改报**超额量**——
超过阈值多少，而不是命中几个。超额量有下界 0 且可被真实降低，因此可跨时间比较。

口径（判据全文与门限见 `policy/structural_budget.md`）：

    C = Σ max(0, CC − 10) + Σ max(0, 认知 − 15)                 复杂度超额
    L = Σ max(0, 函数行 − 80)
      + Σ max(0, 类规模 − 阈值)                                  规模超额
          类体 ≥ 60% 文件行（"模块即类"）→ 度量改为文件行、阈值 800
          否则 → 度量类体行、阈值 450
    D = Σ max(0, 重复对 tokens − 12)                             重复超额
    S = C + L + D                                                总分（越低越好）

C 与 D 需要外部二进制 `bifrost`（Python 侧审计，见 `policy/bifrost_audit.md`）；
L 与"模块即类"判定是纯 AST，无外部依赖。本工具**不进日常门禁**。

用法：
    python tools/structural_score.py              # 打印各分量与总分
    python tools/structural_score.py --save       # 写基线（tools/structural_baseline.json）
    python tools/structural_score.py --compare    # 与基线比较，列出新增项（回归）
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

# ── 口径常量（改动须同步 policy/structural_budget.md）──────────────────────
SKIP_DIRS = ("tests", "_drafts", "dist", ".git", "__pycache__", "egg-info", ".agents")
CC_BASE = 10                     # 工具阈值（提示线）
COG_BASE = 15
FUNC_LIMIT = 120                 # 内部线 = 阈值 × 1.5
CLASS_LIMIT = 450
MODULE_LIMIT = 800
MODULE_SCOPE_RATIO = 0.60        # 类体占文件行比例 ≥ 此值 → 按模块度量
CLONE_MIN_TOKENS = 12            # 重复工具的 minTokens
CLONE_ENTITY_TOKENS = 40         # 实体级重复门槛（≤ 此值为入口/桩形态，不计入 D）
CLONE_STUB_STMTS = 4             # 入口桩：两侧体无控制流且简单语句 ≤ 此值 → 不计入 D
CLONE_CHUNK = 30                 # 重复工具分块（固定值：分块影响"最佳克隆对"选取）
CC_CHUNK = 20                    # 复杂度/规模工具分块（工具每调用最多 25 文件）
EXEMPT_PREFIXES = ("policy.",)   # 制度执行者（各自独立、可单跑，判保持）

_CC_RE = re.compile(r"^- (.+): (\d+) \(in .+\)$")
_COG_RE = re.compile(r"^- (.+): (\d+)$")


@dataclass
class Item:
    """一条超额项（用于 --compare 的"新命中"判定）。"""

    family: str      # CC / COG / FUNC / CLASS / CLONE
    key: str         # 符号全名或重复对键
    excess: int      # 超额量
    detail: str = ""


@dataclass
class Score:
    """四个分量与明细。"""

    cc: int = 0
    cog: int = 0
    func: int = 0
    cls: int = 0
    clone: int = 0
    items: list[Item] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.cc + self.cog + self.func + self.cls + self.clone


# ── 文件集 ──────────────────────────────────────────────────────────────────

def _py_files(root: pathlib.Path) -> list[str]:
    """扫描面：非 tests 的受控 Python 文件（相对仓库根的 posix 路径）。

    与外部裁判同口径：排除 tests / _drafts / .agents / 构建产物目录（`policy/`
    与 `tools/` 属产品自查面，**在**扫描内）。
    """
    out = []
    for p in root.rglob("*.py"):
        parts = p.relative_to(root).parts[:-1]
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        out.append(p.relative_to(root).as_posix())
    return sorted(out)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# ── Bifrost 调用 ────────────────────────────────────────────────────────────

def _bifrost(root: pathlib.Path, tool: str, args: dict) -> str:
    """跑一次外部工具，返回报表文本；二进制不可用时给出可执行的提示。"""
    cmd = ["bifrost", "--root", str(root), "--tool", tool, "--args", json.dumps(args)]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", shell=True, timeout=900
        )
    except FileNotFoundError as exc:  # pragma: no cover - 环境缺失路径
        raise SystemExit("[SKIP] 未找到 bifrost 二进制（见 policy/bifrost_audit.md）") from exc
    try:
        return json.loads(res.stdout)["structuredContent"]["report"]
    except (json.JSONDecodeError, KeyError) as exc:  # pragma: no cover
        raise SystemExit(f"[FAIL] {tool} 报表解析失败：{res.stdout[:200]!r}") from exc


def _max_by_fqn(report: str, pattern: re.Pattern) -> dict[str, int]:
    """报表行 → {符号全名: 值}（同一符号重复出现取最大值）。"""
    out: dict[str, int] = {}
    for line in report.splitlines():
        m = pattern.match(line.strip())
        if m:
            fqn, value = m.group(1), int(m.group(2))
            out[fqn] = max(out.get(fqn, 0), value)
    return out


def _complexity_items(root: pathlib.Path, files: list[str]) -> list[Item]:
    """C 分量：CC 与认知复杂度的超额量。"""
    items: list[Item] = []
    for tool, pattern, base, family in (
        ("compute_cyclomatic_complexity", _CC_RE, CC_BASE, "CC"),
        ("compute_cognitive_complexity", _COG_RE, COG_BASE, "COG"),
    ):
        values: dict[str, int] = {}
        for chunk in _chunks(files, CC_CHUNK):
            args = {"file_paths": chunk, "max_findings": 500, "threshold": base}
            for fqn, val in _max_by_fqn(_bifrost(root, tool, args), pattern).items():
                values[fqn] = max(values.get(fqn, 0), val)
        items.extend(
            Item(family, fqn, val - base, f"{family} {val}")
            for fqn, val in sorted(values.items())
            if val > base
        )
    return items


def _cell_fqn(cell: str) -> str:
    """报表单元 `` `fqn` (path) `` → fqn。"""
    return cell.strip().lstrip("`").split("`", 1)[0]


def _cell_path(cell: str) -> str:
    """报表单元 `` `fqn` (path) `` → 仓库相对路径（统一分隔符）。"""
    m = re.search(r"\(([^)]+)\)\s*$", cell.strip())
    return m.group(1).replace("\\", "/") if m else ""


_COMPOUND = (ast.For, ast.While, ast.If, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)


def _is_thin_stub(root: pathlib.Path, path: str, name: str) -> bool:
    """该定义体是否"薄"：无控制流（无复合语句）且去 docstring 后语句数 ≤ 阈值。

    真·转调共享实现的体是直线：样板 `del`/赋值 + 一句调用或 return。带 `for`/`if`
    的体即使语句少也含真实逻辑，不算薄（避免把"碰巧短"当成"共性已抽"）。
    """
    src_file = root / path
    if not src_file.exists():
        return False
    try:
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name != name:
            continue
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]          # 去掉 docstring
        if any(isinstance(s, _COMPOUND) for s in body):
            return False
        return len(body) <= CLONE_STUB_STMTS
    return False


def _is_entry_stub(root: pathlib.Path, sym: str, peer: str) -> bool:
    """是否"薄入口"对：两侧定义体都是无控制流的直线体（注册面要求的具名入口）。

    注册面（`@register` 原语、handler 表、`get_*` 声明读取）要求一个名一个函数，
    体里只剩"转调共享实现 + 协议样板"；这类对的相似度全在装饰器/签名/docstring/
    样板实参上。判据是"**是否还有未共享的逻辑**"，故按体形态判，不按 token 数判。
    """
    return all(
        _is_thin_stub(root, _cell_path(c), _cell_fqn(c).rsplit(".", 1)[-1])
        for c in (sym, peer)
    )


def _clone_rows(report: str) -> dict[tuple[str, str], int]:
    """重复报表的表格行 → {两侧符号对: tokens}（同一对取较大 tokens）。

    列：`Score | Tokens | Symbol | Peer Symbol | Reasons | Excerpt` → 取 1/2/3 列。
    """
    pairs: dict[tuple[str, str], int] = {}
    for line in report.splitlines():
        if not line.startswith("| ") or "Score" in line or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split(" | ")]
        if len(cells) < 4 or not cells[1].isdigit():
            continue
        sym, peer = cells[2], cells[3]
        if sym == peer:
            continue
        key = (sym, peer) if sym <= peer else (peer, sym)
        pairs[key] = max(pairs.get(key, 0), int(cells[1]))
    return pairs


def _is_entity_dup(root: pathlib.Path, sym: str, peer: str, tokens: int) -> bool:
    """是否计作实体级重复：超门槛，且**不是**以下两类保持项。

    - ≤ `CLONE_ENTITY_TOKENS` 的对：具名入口/桩形态（共性已抽，残留只是入口样板）
    - 两侧定义体都 ≤ `CLONE_STUB_STMTS` 语句的"薄入口"对（注册面要求一个名一个函数）
    - 两侧都在 `policy/`：制度执行者刻意各自独立、可单跑
    """
    if tokens <= CLONE_ENTITY_TOKENS:
        return False
    if all(_cell_fqn(c).startswith(EXEMPT_PREFIXES) for c in (sym, peer)):
        return False
    return not _is_entry_stub(root, sym, peer)


def _clone_items(root: pathlib.Path, files: list[str]) -> list[Item]:
    """D 分量：实体级重复对的 token 超额量（按对去重，计入门槛见 `_is_entity_dup`）。"""
    pairs: dict[tuple[str, str], int] = {}
    for chunk in _chunks(files, CLONE_CHUNK):
        args = {"file_paths": chunk, "min_score": 90, "max_findings": 500}
        for (sym, peer), tokens in _clone_rows(
            _bifrost(root, "report_structural_clone_smells", args)
        ).items():
            if _is_entity_dup(root, sym, peer, tokens):
                pairs[(sym, peer)] = max(pairs.get((sym, peer), 0), tokens)
    return [
        Item("CLONE", f"{_cell_fqn(a)} <-> {_cell_fqn(b)}", tok - CLONE_MIN_TOKENS, f"{tok} tok")
        for (a, b), tok in sorted(pairs.items())
    ]


# ── L 分量（纯 AST，无外部依赖）─────────────────────────────────────────────

def _scale_items(root: pathlib.Path, files: list[str]) -> list[Item]:
    """L 分量：函数行与类规模的超额量（含"模块即类"豁免）。"""
    items: list[Item] = []
    for rel in files:
        src = (root / rel).read_text(encoding="utf-8")
        module_lines = src.count("\n") + 1
        for node in ast.walk(ast.parse(src)):
            item = _scale_item(rel, node, module_lines)
            if item is not None:
                items.append(item)
    return items


def _scale_item(rel: str, node: ast.AST, module_lines: int) -> Item | None:
    """单个 AST 节点的规模超额项（函数行 / 类规模；不超标返回 None）。"""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        lines = (node.end_lineno or node.lineno) - node.lineno + 1
        if lines > FUNC_LIMIT:
            return Item("FUNC", f"{rel}:{node.name}", lines - FUNC_LIMIT, f"{lines} 行")
        return None
    if not isinstance(node, ast.ClassDef):
        return None
    return _class_item(rel, node, module_lines)


def _class_item(rel: str, node: ast.ClassDef, module_lines: int) -> Item | None:
    """类规模超额项：模块即类时按文件行度量（拆类不缩小模读面），否则按类体行。"""
    body = (node.end_lineno or node.lineno) - node.lineno + 1
    if body / module_lines >= MODULE_SCOPE_RATIO:
        if module_lines > MODULE_LIMIT:
            return Item("CLASS", f"{rel}:{node.name}", module_lines - MODULE_LIMIT,
                        f"模块即类 {module_lines} 行（类体 {body}）")
        return None
    if body > CLASS_LIMIT:
        return Item("CLASS", f"{rel}:{node.name}", body - CLASS_LIMIT, f"类体 {body} 行")
    return None


# ── 组装与输出 ──────────────────────────────────────────────────────────────

def compute(root: pathlib.Path, components: set[str]) -> tuple[Score, int]:
    """按需计算分量（components ⊆ {C, L, D}）→ (分数, 扫描文件数)。

    已判保持的项（`tools/structural_kept.json`）在计入前剔除——保持是结论，
    不是待办；没有登记理由的项不剔除，否则指标可被“默默豁免”掉。
    """
    files = _py_files(root)
    kept = _load_kept(root)
    score = Score()
    if "C" in components:
        for item in _complexity_items(root, files):
            score.items.append(item)
            if item.family == "CC":
                score.cc += item.excess
            else:
                score.cog += item.excess
    if "L" in components:
        for item in _scale_items(root, files):
            score.items.append(item)
            if item.family == "FUNC":
                score.func += item.excess
            else:
                score.cls += item.excess
    if "D" in components:
        for item in _clone_items(root, files):
            if f"CLONE|{item.key}" in kept:
                continue
            score.items.append(item)
            score.clone += item.excess
    return score, len(files)


def _print_score(score: Score, components: set[str], n_files: int) -> None:
    print(f"扫描面：{n_files} 个非 tests Python 文件（排除 {', '.join(SKIP_DIRS)}）")
    rows = [("C", "复杂度超额", score.cc + score.cog, "CC / 认知"),
            ("L", "规模超额", score.func + score.cls, "函数行 / 类规模"),
            ("D", "重复超额", score.clone, "重复对 token")]
    for key, label, value, note in rows:
        if key in components:
            print(f"  {label:<8} {value:>6}   （{note}）")
    print(f"  {'结构欠账分 S':<8} {score.total:>6}")
    by_family: dict[str, list[Item]] = {}
    for item in score.items:
        by_family.setdefault(item.family, []).append(item)
    for family in ("CC", "COG", "FUNC", "CLASS", "CLONE"):
        bucket = sorted(by_family.get(family, []), key=lambda i: -i.excess)
        if bucket:
            print(f"    [{family}] {len(bucket)} 项，超额合计 {sum(i.excess for i in bucket)}")
            for item in bucket[:5]:
                print(f"        {item.excess:>5}  {item.key}  ({item.detail})")


def _baseline_path(root: pathlib.Path) -> pathlib.Path:
    return root / "tools" / "structural_baseline.json"


def _kept_path(root: pathlib.Path) -> pathlib.Path:
    return root / "tools" / "structural_kept.json"


def _load_kept(root: pathlib.Path) -> dict[str, str]:
    """判保持登记表 {族|项键: 理由}（缺文件则空表）。"""
    path = _kept_path(root)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("items", {}))


def _load_baseline(root: pathlib.Path) -> dict:
    path = _baseline_path(root)
    if not path.exists():
        raise SystemExit(f"[SKIP] 基线不存在：{path}（先跑 --save）")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_baseline(root: pathlib.Path, score: Score) -> None:
    payload = {
        "total": score.total,
        "components": {"C": score.cc + score.cog, "L": score.func + score.cls, "D": score.clone},
        "items": {f"{i.family}|{i.key}": i.excess for i in score.items},
    }
    _baseline_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"已写基线：{_baseline_path(root)}（S = {score.total}）")


def _compare(root: pathlib.Path, score: Score) -> int:
    """与基线比较：存量项按批次消化，**新增项才算回归**（退出码 1）。"""
    base = _load_baseline(root)
    old = base["items"]
    new = {f"{i.family}|{i.key}": i.excess for i in score.items}
    added = [(k, v) for k, v in new.items() if k not in old]
    grew = [(k, v, old[k]) for k, v in new.items() if k in old and v > old[k]]
    gone = [k for k in old if k not in new]
    print(f"基线 S = {base['total']} → 当前 S = {score.total}（Δ {score.total - base['total']:+d}）")
    print(f"  消除 {len(gone)} 项 / 新增 {len(added)} 项 / 变大 {len(grew)} 项")
    for key, value in sorted(added, key=lambda kv: -kv[1]):
        print(f"    [新增] +{value:<5} {key}")
    for key, value, before in sorted(grew, key=lambda kv: -(kv[1] - kv[2])):
        print(f"    [变大] {before} → {value}  {key}")
    return 1 if (added or grew) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural_score", description="结构欠账分（口径见 policy/structural_budget.md）")
    parser.add_argument("--component", action="append", choices=["C", "L", "D"],
                        help="只算指定分量（可重复；缺省全算）")
    parser.add_argument("--save", action="store_true", help="写基线 tools/structural_baseline.json")
    parser.add_argument("--compare", action="store_true", help="与基线比较（新增即回归，退出码 1）")
    args = parser.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parent.parent
    components = set(args.component or ["C", "L", "D"])
    score, n_files = compute(root, components)
    _print_score(score, components, n_files)
    if args.save:
        _save_baseline(root, score)
    if args.compare:
        return _compare(root, score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
