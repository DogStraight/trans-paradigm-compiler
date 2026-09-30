"""tests/policy/test_fuzz_shrink.py — fuzz 回馈链路后两步的自测。

被测：`tests/fuzz/shrink.py`（ddmin 最小化 + 沉淀）、`tests/edge/run_edge.py`
的沉淀语料不变量复检、`tests/fuzz/oracle.py` 的违反判定、`tests/fuzz/generate.py`
的种子收集。

分五层（各证一件事，互不替代）：

1. **算法层**：ddmin 用**合成谓词**（无管线）——证"最小 + 1-minimal + 保 interestingness"；
2. **文本层**：`shrink_text` 的行级/行内收缩在合成谓词下逐级生效；
3. **链路层**：注入式假管线（monkeypatch `oracle.format_source`）跑
   finding → 最小化 → 沉淀 → 抬头 → 门禁复检的**完整文件路径**；
4. **判据层**：`non-idempotent` 的已接受偏差（展开路径 / 一遍收敛的空白漂移）记
   advisory 不判违反，两道否决（不收敛、非空白改动）各自可单独推翻豁免；
5. **种子层**：种子集只收输入语料（跳过流水线输出目录）且与文件系统遍历序无关。

⚠ 第 3 层用假管线是**刻意的**：真实链路要求"有一个当前仍在复现的缺陷"，而本轮
实测 C 包 4000 轮 fuzz 0 findings（真实缺陷都已修），拿真实输入无法同时演示
"未修则拒沉淀"与"已修则沉淀成功"两侧。假管线只替换"被测程序"，本模块的
最小化/沉淀/抬头/门禁代码走的是真实路径（真实文件读写）。
Doc: tests/fuzz/README.md（回馈链路）；docs/references.md（shrinking 参照）
"""

from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, "tests", "fuzz"), os.path.join(_ROOT, "tests", "edge")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import oracle  # noqa: E402
import run_edge  # noqa: E402
import shrink  # noqa: E402


# ── 1. 算法层：ddmin ───────────────────────────

class TestDdmin:
    def test_reduces_to_minimal_core(self):
        # 谓词只关心 "c" 与 "f" 同时在 → 最小子集恰为这两个
        units = list("abcdefgh")
        out = shrink.ddmin(units, lambda cs: "c" in cs and "f" in cs)
        assert out == ["c", "f"]

    def test_keeps_interestingness(self):
        units = list("xxBUGyy")
        pred = lambda cs: "BUG" in "".join(cs)
        out = shrink.ddmin(units, pred)
        assert pred(out)

    def test_is_one_minimal(self):
        # 1-minimal：再去掉任意一个单元就不再 interesting
        units = list("aXbYcZ")
        pred = lambda cs: "X" in cs and "Z" in cs
        out = shrink.ddmin(units, pred)
        assert pred(out)
        for i in range(len(out)):
            assert not pred(out[:i] + out[i + 1:]), f"去掉第 {i} 个仍 interesting → 非 1-minimal"

    def test_empty_and_single(self):
        assert shrink.ddmin([], lambda cs: True) == []
        assert shrink.ddmin(["a"], lambda cs: True) == ["a"]

    def test_split_balanced(self):
        assert [len(c) for c in shrink._split(list(range(7)), 3)] == [3, 2, 2]
        assert [len(c) for c in shrink._split(list(range(4)), 2)] == [2, 2]
        # n 超过长度 → 退化为每单元一块
        assert [len(c) for c in shrink._split(list(range(2)), 9)] == [1, 1]


# ── 2. 文本层：shrink_text ─────────────────────

class TestShrinkText:
    def test_line_level_drops_irrelevant_lines(self):
        src = "noise one\nkeep BUG here\nnoise two\nnoise three\n"
        text, log = shrink.shrink_text(src, lambda s: "BUG" in s)
        # 行级 ddmin 先把无关行整行丢掉，行内字符级再把行内无关字符缩掉
        # （合成谓词只认 "BUG"，故最终可到 3 字节——这里断言"强收缩 + 两条 pass 都跑了"）
        assert "BUG" in text and len(text) <= len("keep BUG here")
        assert any("行级" in s for s in log)
        assert any("字符级" in s for s in log)

    def test_char_level_shortens_within_line(self):
        # 单行 finding：行级无事可做，靠行内字符级缩（对应真实个案：
        # C 包非幂等样本是一条 86 字节单行，能缩的是注释长度）
        src = "a" + "x" * 40 + "BUG" + "y" * 40 + "z\n"
        text, log = shrink.shrink_text(src, lambda s: "BUG" in s)
        assert "BUG" in text
        assert len(text) < 20, f"行内字符级没生效：{text!r}"
        assert any("字符级" in s for s in log)

    def test_preserves_trailing_newline_state(self):
        for src in ("BUG\n", "BUG"):
            text, _ = shrink.shrink_text(src, lambda s: "BUG" in s)
            assert text.endswith("\n") == src.endswith("\n")

    def test_budget_exhaustion_is_safe(self):
        # 预算到顶后谓词一律返回 False：不得出现"越缩越错"（产出仍须 interesting）
        calls = {"n": 0}

        def pred(s: str) -> bool:
            calls["n"] += 1
            return calls["n"] <= 3 and "BUG" in s

        src = "BUG\n" * 5
        text, _ = shrink.shrink_text(src, pred)
        assert "BUG" in text


# ── 3. 链路层：注入式假管线 ────────────────────

class _FakePipeline:
    """假"被测程序"：含 BUG 的输入崩；含 NONIDEM 的输入首遍成功但幂等性被破坏。

    两种形态刻意都留着：崩溃那类 `expectation_of` 也能挡（崩溃 → unfixed），
    **非幂等**那类 `success=True` ⇒ `expectation_of` 会判 clean ⇒ 只有"类别仍复现"
    这道闸能挡——它是这条闸唯一的判别性用例（实测：拆掉该闸时崩溃用例照样绿）。
    """

    def __init__(self):
        self.fixed = False
        self.calls = 0

    def __call__(self, src: str, rules_dir: str, ext_dirs=None) -> dict:
        self.calls += 1
        if not self.fixed:
            if "BUG" in src:
                raise RuntimeError("injected crash")
            if "NONIDEM" in src:
                # 每遍都多一个 "#"：success=True，但 format(format(x)) != format(x)
                return {"success": True, "output": src + "#", "error": None}
        return {"success": True, "output": src, "error": None}


@pytest.fixture
def fake_pipeline(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setattr(oracle, "format_source", fake)
    return fake


def _make_finding(d: str, name: str, src: str, kind: str) -> str:
    path = os.path.join(d, name)
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    with open(os.path.join(d, shrink._INDEX_NAME), "a", encoding="utf-8") as f:
        f.write(f'{{"file": "{name}", "kind": "{kind}", "label": "gen"}}\n')
    return path


def _run(path, tmp_path, *, sediment=None, cause=None, name=None):
    """按 CLI 的取数路径调 shrink_one：类别优先取 findings 索引。"""
    fdir = os.path.dirname(path)
    rec = shrink.load_records(fdir).get(os.path.basename(path))
    return shrink.shrink_one(
        path, pack="grammar/verilog", ext_dirs=[], lexer=None,
        kind=(rec or {}).get("kind"), label=(rec or {}).get("label", "gen"),
        out_dir=str(tmp_path / "min"), token_pass=False,
        max_tests=400, sediment_root=sediment, cause=cause, name=name,
        rec=rec, force=False, trace=False,
    )


class TestChain:
    def test_minimize_then_refuse_sediment_while_live(self, fake_pipeline, tmp_path):
        """缺陷活着：能最小化，但沉淀必须被**拒**（不能把未修缺陷固化成期望）。"""
        fdir = tmp_path / "findings"
        path = _make_finding(
            str(fdir), "00001_crash_gen.v",
            "head\nline BUG line\n" + "tail\n" * 6, "crash",
        )
        edge = tmp_path / "corpus"
        r = _run(path, tmp_path, sediment=str(edge), cause="注入崩溃")
        assert r["minimized"] is True
        assert r["after_bytes"] < r["before_bytes"]
        assert "BUG" in open(r["out"], encoding="utf-8").read()
        assert r["sedimented"] is False
        # 断言到**具体**那道闸（"先修再沉淀"两句文案相同，只断言它不具判别性：
        # 拆掉"类别仍复现"闸时崩溃用例照样绿——实测过）
        assert "类别 crash 仍在复现" in r["sediment_info"]
        assert not os.path.isdir(str(edge / "clean"))

    def test_refuse_sediment_for_live_nonidempotence(self, fake_pipeline, tmp_path):
        """判别性用例：`success=True` 的活缺陷——只有"类别仍复现"这道闸能挡。

        真实对应：C 包的注释折行漂移（非幂等，`success=True`）。实测踩过坑：
        只按 `success` 判 clean/reject 时，它被当成 clean 写进了 clean/。
        """
        fdir = tmp_path / "findings"
        path = _make_finding(str(fdir), "00005_non-idempotent_gen.v",
                             "req NONIDEM tail\n", "non-idempotent")
        edge = tmp_path / "corpus"
        r = _run(path, tmp_path, sediment=str(edge), cause="注入非幂等")
        assert r["sedimented"] is False
        assert "类别 non-idempotent 仍在复现" in r["sediment_info"]
        assert not os.path.isdir(str(edge / "clean")), (
            "非幂等仍复现却被判 clean 写进去了——沉淀闸失效"
        )

    def test_sediment_after_fix_writes_provenance_header(self, fake_pipeline, tmp_path):
        """修完之后那一遍：走沉淀分支，抬头写明判定 + 类别，且能落进 reject/clean。"""
        fdir = tmp_path / "findings"
        path = _make_finding(str(fdir), "00002_crash_gen.v", "BUG\n", "crash")
        fake_pipeline.fixed = True
        edge = tmp_path / "corpus"
        r = _run(path, tmp_path, sediment=str(edge), cause="注入崩溃",
                 name="injected_crash.v")
        assert r["minimized"] is False  # 已修 → 不再最小化，直接沉淀
        assert r["sedimented"] is True
        written = r["sediment_info"]
        text = open(written, encoding="utf-8").read()
        assert written.endswith(os.path.join("clean", "injected_crash.v"))
        assert text.startswith("// edge clean（fuzz 回归 ")
        assert "注入崩溃" in text
        assert "fuzz 类别 crash" in text
        assert text.endswith("BUG\n")

    def test_sediment_refuses_existing_without_force(self, fake_pipeline, tmp_path):
        fdir = tmp_path / "findings"
        path = _make_finding(str(fdir), "00003_crash_gen.v", "BUG\n", "crash")
        fake_pipeline.fixed = True
        edge = tmp_path / "corpus"
        kw = dict(sediment=str(edge), cause="注入崩溃", name="dup.v")
        assert _run(path, tmp_path, **kw)["sedimented"] is True
        second = _run(path, tmp_path, **kw)
        assert second["sedimented"] is False
        assert "--force" in second["sediment_info"]

    def test_skip_when_fixed_and_no_sediment(self, fake_pipeline, tmp_path):
        fdir = tmp_path / "findings"
        path = _make_finding(str(fdir), "00004_crash_gen.v", "BUG\n", "crash")
        fake_pipeline.fixed = True
        r = _run(path, tmp_path)
        assert r.get("skipped") and "已修" in r["skipped"]

    def test_unknown_kind_without_index_is_skipped(self, fake_pipeline, tmp_path):
        path = os.path.join(str(tmp_path), "orphan.v")
        with open(path, "w", encoding="utf-8") as f:
            f.write("plain text, no bug\n")
        r = _run(path, tmp_path)
        assert r.get("skipped")

    def test_infer_kind_without_index(self, fake_pipeline, tmp_path):
        # 无索引但当前代码下确实复现 → 现测类别（兜底路径）
        path = os.path.join(str(tmp_path), "noidx.v")
        with open(path, "w", encoding="utf-8") as f:
            f.write("BUG\n")
        r = _run(path, tmp_path)
        assert r["kind"] == oracle.CRASH
        assert r["minimized"] is True


# ── 门禁：沉淀语料的不变量复检 ─────────────────

class TestEdgeInvariantRecheck:
    def test_header_kind_parsed(self):
        src = ("// edge clean（fuzz 回归 2026-09-26）: 成因。\n"
               "// fuzz 类别 non-idempotent；最小复现 86→81 字节。\ncode\n")
        assert run_edge._fuzz_kind(src) == "non-idempotent"
        assert run_edge._fuzz_kind("// edge: 手写语料\nmodule m;\n") is None

    def test_regressed_invariant_is_reported(self, fake_pipeline):
        """抬头登记了类别、但该类别又复现 → 门禁必须报（只判 clean/reject 挡不住）。"""
        failures: list[str] = []
        src = "// edge clean（fuzz 回归 2026-09-26）: x。\n// fuzz 类别 crash；y。\nBUG\n"
        # 假管线仍是"未修"状态 → crash 复现
        assert run_edge._kind_violation(src, "grammar/verilog", "x.v", failures) is None
        assert any("INVARIANT-REGRESSED" in f for f in failures)

    def test_clean_case_passes_recheck(self, fake_pipeline):
        fake_pipeline.fixed = True
        failures: list[str] = []
        src = "// edge clean（fuzz 回归 2026-09-26）: x。\n// fuzz 类别 crash；y。\nBUG\n"
        assert run_edge._kind_violation(src, "grammar/verilog", "x.v", failures) == "crash"
        assert failures == []


# ── 4. oracle 判据面：已接受偏差（advisory）vs 真违反 ───────────────

class TestOracleAcceptedDrift:
    """`non-idempotent` 的两类已接受偏差记 advisory、不判违反（2026-09-30 判据化）。

    判据来源 `docs/gaps/gap-formatter-line-behavior.md` #3（展开路径）/ #5、#7
    （一遍收敛的空白漂移）。判别性关键：**"不收敛"与"非空白改动"各自单独就能
    推翻豁免**，故下面既证接受侧、也证两道否决。
    """

    @staticmethod
    def _eval(monkeypatch, fake, src: str, label: str = "gen"):
        monkeypatch.setattr(oracle, "format_source", fake)
        advisories: list[str] = []
        violations = oracle.evaluate_format(
            src, None, rules_dir="grammar/verilog", ext_dirs=[], label=label,
            advisories=advisories,
        )
        return violations, advisories

    def test_settled_whitespace_drift_is_advisory(self, monkeypatch):
        """一遍补平后稳定（真实现场形态：`/**/)` → `/**/ )`）⇒ advisory，不判违反。

        假管线照真实三步走：源（注释独立成行）→ 首遍把注释贴到 `)` 前 → 二遍补一格
        → 三遍起稳定。三步用转移表写死，避免"假管线自己先收敛"把现场做没。
        """
        transitions = {
            "f(a)\n": "f(a /**/);\n",          # 首遍：注释回插，贴住 `)`
            "f(a /**/);\n": "f(a /**/ );\n",   # 二遍：formatter 补一格
        }

        def fake(src: str, rules_dir: str, ext_dirs=None) -> dict:
            return {"success": True, "output": transitions.get(src, src), "error": None}

        violations, advisories = self._eval(monkeypatch, fake, "f(a)\n")
        assert violations == []
        assert len(advisories) == 1 and "空白漂移" in advisories[0]

    def test_whitespace_drift_without_settling_is_violation(self, monkeypatch):
        """差异只在空白，但**不收敛**（来回补格）⇒ 仍判违反（豁免不是"空白即放过"）。"""
        def fake(src: str, rules_dir: str, ext_dirs=None) -> dict:
            out = src[:-1] if src.endswith("  ") else src + " "
            return {"success": True, "output": out, "error": None}

        violations, advisories = self._eval(monkeypatch, fake, "f(a)\n")
        assert [v.kind for v in violations] == [oracle.NON_IDEMPOTENT]
        assert advisories == []

    def test_growing_output_is_violation(self, monkeypatch):
        """非收敛 + 非空白（每遍多一个 `#`）⇒ 判违反（与链路层假管线同一形态）。"""
        def fake(src: str, rules_dir: str, ext_dirs=None) -> dict:
            return {"success": True, "output": src + "#", "error": None}

        violations, advisories = self._eval(monkeypatch, fake, "keep\n")
        assert [v.kind for v in violations] == [oracle.NON_IDEMPOTENT]
        assert advisories == []

    def test_comment_repositioning_is_violation(self, monkeypatch):
        """注释**换位**（C 包折行漂移形态）⇒ 压掉空白后不同 ⇒ 仍判违反。

        现场实测：`int first /* x×60 */, second;` 首遍把注释留在 `first,` 之后、二遍
        移到 `second` 之后（跨 token 移动）——不是"位置不动、仅邻接空白补平"，故
        不在 advisory 面内（README 里刻着这条别并成一条）。
        """
        transitions = {
            "int a, /*c*/ b;\n": "int a, /*c*/\n b;\n",     # 首遍：注释留在 `first,` 侧
            "int a, /*c*/\n b;\n": "int a,\n b /*c*/;\n",   # 二遍：注释换位到 `second` 侧
        }

        def fake(src: str, rules_dir: str, ext_dirs=None) -> dict:
            return {"success": True, "output": transitions.get(src, src), "error": None}

        violations, advisories = self._eval(monkeypatch, fake, "int a, /*c*/ b;\n")
        assert [v.kind for v in violations] == [oracle.NON_IDEMPOTENT]
        assert advisories == []

    def test_expansion_path_is_advisory_even_when_growing(self, monkeypatch):
        """含宏/指令 marker ⇒ 镜像 `pipeline._check_idempotent`：连"每遍增长"也不判违反。"""
        def fake(src: str, rules_dir: str, ext_dirs=None) -> dict:
            return {"success": True, "output": src + "#", "error": None}

        violations, advisories = self._eval(monkeypatch, fake, "`define A 1\nkeep\n")
        assert violations == []
        assert len(advisories) == 1 and "展开路径" in advisories[0]


# ── 5. 种子集：只收输入语料 + 顺序跨平台一致 ───────────────────

class TestSeedCollection:
    """`generate.collect_seeds`：种子集不得随本机产物/文件系统遍历序变化。

    真实事故（2026-09-29）：本机残留 66 个 `gen/*.v` ⇒ 种子 185 个而 CI 119 个，
    同一 `--seed` 两边抽不同序列，CI 报的 finding 本机复现不出。
    """

    @staticmethod
    def _tree(root) -> None:
        for rel in ("normal/a.v", "normal/gen/gen_a.v", "macro/ast/x.v",
                    "edge/lex/lex.json", "edge/b.v", "normal/notes.txt"):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("module m;\n", encoding="utf-8")

    def test_excludes_pipeline_output_dirs(self, tmp_path):
        import generate

        self._tree(tmp_path)
        got = [os.path.relpath(p, str(tmp_path)).replace(os.sep, "/")
               for p in generate.collect_seeds(str(tmp_path))]
        assert got == ["edge/b.v", "normal/a.v"]  # gen/ast/lex 不是输入语料

    def test_order_independent_of_filesystem_walk_order(self, tmp_path, monkeypatch):
        """`os.walk` 的目录序是文件系统相关的——结果必须与它无关（确定性）。"""
        import generate

        self._tree(tmp_path)
        expected = generate.collect_seeds(str(tmp_path))

        real_walk = os.walk

        def reversed_walk(root, *a, **kw):
            # 必须在**被 yield 的列表**上原地改：`os.walk` 的剪枝协议就靠这个列表
            # （换新列表 ⇒ 子目录该不该下探的剪枝失效，测试自己会造假阳性）
            for dirpath, dirnames, names in real_walk(root, *a, **kw):
                dirnames.reverse()
                names.reverse()
                yield dirpath, dirnames, names

        monkeypatch.setattr(generate.os, "walk", reversed_walk)
        assert generate.collect_seeds(str(tmp_path)) == expected
