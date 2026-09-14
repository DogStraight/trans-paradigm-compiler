"""tools/check_gate_efficacy.py — 门禁有效性抽查（变异测试的清单化版本）。

Doc: AGENTS.md（运行节：测试门禁）

动机：门禁的全部价值在于它会红——但这个性质是门禁自身的属性，**没有任何
测试在测它**。历史上这里做过几次回退验证（把修复改回去、确认测试变红），
那些动作都是一次性的：门禁哪天失效没人知道，而"绿"看起来完全一样。

做法：清单里每条变异都**来自真实发生过的事故**（不是想象的），逐条执行
    备份 → 应用文本变异 → 跑指定测试 → **期望失败** → 还原
若在某条变异下测试仍然通过，说明该门禁已失效（或测试被削弱）→ 报错。

设计取舍：
- **变异点只从真实事故取**：想象的变异无法证明门禁挡住了它该挡的东西；
  每条都带 `why`（当年怎么发现的），让清单本身可审查。
- **测试用文件级而非用例级**：源码重构会改名用例，文件级更稳（本清单要活
  很久，锚点漂移的代价高于精确度收益）；文件里任一用例变红即算通过。
- **锚点找不到就报错**：源码变了导致变异无法施加时，报清单过时而非静默
  跳过——静默跳过会让抽查慢慢变成空转（和门禁假绿同一个病）。
- **不进日常门禁**：每条要跑一次相关测试，全清约一分钟；定位同
  `eval_benchmark.py`（人工/定期跑）。
- **要求工作区干净**：变异会临时改写源码，脏工作区下还原会掩盖未提交改动。

用法：
    python tools/check_gate_efficacy.py            # 跑全部变异
    python tools/check_gate_efficacy.py --list     # 只列清单
    python tools/check_gate_efficacy.py --only 3   # 只跑第 3 条（从 1 起）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 每条变异 = 一个真实事故 + 它应该触发的那道门。
_MUTATIONS: list[dict[str, str]] = [
    {
        "why": "NC008 曾长期是死规则：GenvarDecl 的 name_attr 取不到名字 → 符号"
               "从未注册 → 判定永不触发（0.1.2 收尾轮评测扩面时发现）",
        "file": "grammar/verilog/02_declarations/40_params.toml",
        "old": 'name_attr = "genvar_names.content"',
        "new": 'name_attr = "genvar_names.name"',
        "test": "tests/languages/verilog/test_name_convention.py",
    },
    {
        "why": "slot_runner 的 result=extra 曾误把 handler 返回值接回 AST → typed_ports"
               " wrapper 被内联进主输出（保真度 1.0→0.43），由真实语料 e2e 抓到",
        "file": "transform/slot_runner.py",
        "old": "                if result == \"extra\":\n"
               "                    # 额外产物由 handler 自己出（`mark_extra`）——返回值**不接回**\n"
               "                    # AST（typed_ports build_wrapper 先例：wrapper 是独立文件）。\n"
               "                    new.append(item)\n",
        "new": "                if result == \"extra\":\n"
               "                    new.append(out if isinstance(out, Node) else item)\n",
        "test": "tests/engine/pipeline/test_unit_slot_schedule.py",
    },
    {
        "why": "MH002 的续行保守判定若被去掉，多行宏体会被误判为值不同 → 误报"
               "（实现时即按宁可漏报定调，故该行为必须有测试锁住）",
        "file": "linter/checkers/macro_hygiene.py",
        "old": "                value = None if (self._cont and body.endswith(self._cont)) else body",
        "new": "                value = body",
        "test": "tests/engine/linter/test_linter_macro_hygiene.py",
    },
    {
        "why": "真实语料误报基线门禁（只许减不许增）：若基线被改小而门禁不报，"
               "整个误报面不无声增长的保障就是空的",
        "file": "tests/e2e/samples/real/diag_baseline.json",
        "old": '    "W105": 2,',
        "new": '    "W105": 0,',
        "test": "tests/policy/test_diag_baseline.py",
    },
    {
        "why": "语言作用域重置（2026-09-14 实测事故：同进程先跑 c4 再跑 verilog，"
               "规则表跨语言累积 → 根规则被 c4 的 Program 夺走 → 输出为空；"
               "该现象曾被当作'幽灵 flake'）",
        "file": "parser/__init__.py",
        "old": "    register.begin_language(rules_dir)\n",
        "new": "    pass  # 变异：关掉语言作用域重置\n",
        "test": "tests/engine/core/test_language_switch.py",
    },
]


def _ensure_clean_tree() -> bool:
    """要求工作区干净——变异会临时改源码，脏树下还原会掩盖未提交改动。"""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        print("[error] 无法读取 git 状态（不是 git 仓库？）")
        return False
    dirty = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if dirty:
        print("[error] 工作区不干净，拒绝施加变异（会掩盖未提交改动）：")
        for ln in dirty[:10]:
            print(f"    {ln}")
        print("    先提交或 stash，再跑本工具。")
        return False
    return True


def _run_mutation(m: dict[str, str], index: int) -> tuple[bool, str]:
    """施加变异 → 跑测试 → 还原。返回 (门禁是否如期变红, 说明)。"""
    path = os.path.join(_ROOT, m["file"])
    if not os.path.isfile(path):
        return False, f"文件不存在（清单过时？）：{m['file']}"
    with open(path, encoding="utf-8") as f:
        original = f.read()
    if m["old"] not in original:
        return False, (
            f"变异锚点未找到（源码已变，清单过时）：{m['file']}\n"
            f"      期望锚点：{m['old'].splitlines()[0][:70]}…"
        )
    if original.count(m["old"]) > 1:
        return False, f"变异锚点不唯一（{original.count(m['old'])} 处）：{m['file']}"

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(original.replace(m["old"], m["new"], 1))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", m["test"], "-q", "-n", "0", "--no-header"],
            cwd=_ROOT, capture_output=True, text=True, encoding="utf-8",
        )
    finally:
        with open(path, "w", encoding="utf-8") as f:
            f.write(original)
        with open(path, encoding="utf-8") as f:
            assert f.read() == original, f"还原失败，请手动检查 {m['file']}"

    if proc.returncode != 0:
        return True, "测试如期变红 ✓"
    return False, (
        "测试**仍然通过** ✗ —— 门禁可能已失效，或被削弱的测试掩盖了变异"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="门禁有效性抽查（变异）")
    ap.add_argument("--list", action="store_true", help="只列清单")
    ap.add_argument("--only", type=int, default=None, help="只跑第 N 条（从 1 起）")
    args = ap.parse_args()

    if args.list:
        for i, m in enumerate(_MUTATIONS, 1):
            print(f"{i}. {m['file']}")
            print(f"   变异：{m['old'].splitlines()[0][:70]}… → {m['new'].splitlines()[0][:50]}…")
            print(f"   期望变红：{m['test']}")
            print(f"   来源事故：{m['why']}")
        return 0

    if not _ensure_clean_tree():
        return 2

    selected = list(enumerate(_MUTATIONS, 1))
    if args.only is not None:
        selected = [(i, m) for i, m in selected if i == args.only]
        if not selected:
            print(f"[error] 无第 {args.only} 条")
            return 2

    failures: list[str] = []
    print(f"[info] 抽查 {len(selected)} 条变异（每条跑一次相关测试，约一分钟）\n")
    for i, m in selected:
        print(f"[{i}/{len(_MUTATIONS)}] {m['file']}")
        ok, note = _run_mutation(m, i)
        print(f"        {note}")
        if not ok:
            failures.append(f"{m['file']}（期望 {m['test']} 变红）：{note}")

    print()
    if failures:
        print("[FAIL] 以下变异未如期触发门禁：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] 全部变异都如期变红——这些门禁仍然握着它们该握的东西")
    return 0


if __name__ == "__main__":
    sys.exit(main())
