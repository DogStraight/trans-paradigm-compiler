"""Gate boundary: invariant anchors vs doc anchors must stay disjoint.

Why: `policy/check_invariants.py` and `policy/check_doc_refs.py` both answer
"a declared reference must resolve". They are NOT duplicates -- different
grammar and granularity:
  - doc gate (D1-D4): file-level existence, sources are .md / code Doc: heads
  - invariants gate: symbol-level (rule id / test func / mutation index),
    source is docs/invariants.toml only
This file locks the boundary so the two never silently grow into each other
(that would be the "dual implementation" failure mode).
Doc: docs/invariants.toml
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


inv = _load("ci_boundary", "policy/check_invariants.py")
doc = _load("cdr_boundary", "policy/check_doc_refs.py")


def test_doc_gate_only_owns_markdown() -> None:
    """Doc gate must not try to parse the invariants manifest (no overlap)."""
    names = [p.name for p in doc._iter_doc_files(ROOT)]
    assert all(n.endswith(".md") for n in names), names
    assert "invariants.toml" not in names


def test_invariants_gate_rejects_doc_granularity() -> None:
    """A .md anchor is doc-gate business; invariants gate must refuse it."""
    err = inv.resolve_anchor(ROOT, "docs/decisions/README.md#Impl")
    assert err is not None
    assert "锚点类型" in err


def test_anchor_grammars_are_disjoint() -> None:
    ok = [
        "policy/check_hardcode.py#R6",
        "tests/policy/test_check_hardcode.py::test_rule6_covers_every_protocol_prefix_family",
        "tools/check_gate_efficacy.py#9",
    ]
    for a in ok:
        assert inv.resolve_anchor(ROOT, a) is None, a
    bad = ["docs/invariants.toml#x", "CHANGELOG.md", "no-grammar"]
    for a in bad:
        assert inv.resolve_anchor(ROOT, a) is not None, a
