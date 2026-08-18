# Contributing

## Project Overview

TransParadigm Compiler (tpc) is a configuration-driven compiler frontend.
Language knowledge (tokens, grammar, operators, render layout) lives entirely
in TOML declarations under `grammar/<lang>/`; the engine
(`core/lexer/parser/analyzer/transform/renderer/linter`) is language-agnostic.
c4 and Verilog are the two proofs of language-agnosticism.

## Environment Setup

```powershell
# Dev install (editable + test deps)
pip install -e ".[test]"

# Run full test suite (with coverage gate >= 84%)
python -m pytest tests -q --cov
```

## Directory Layout

```
core/        language-agnostic engine (rule registration / config / plugin loading)
lexer/       lexing (token-config-driven + number-shape generator)
parser/      parsing (rule loading / disambiguation / injection)
analyzer/    semantic analysis (scopes / symbols / primitives)
transform/   AST transforms (primitive registration + plugins)
renderer/    Doc IR + layout algorithm + primitives
linter/      pre-parse token linter (discovery / slicing / multi-path diagnostics)
preprocessor/macros / conditional compilation (primitives + expand/reverse)
grammar/     language packs (verilog / c4) + plugins (typed_ports/formatter/...)
pipeline/    pipeline orchestration (run_pipeline_on_source, shared by CLI and tests)
tests/       tests (engine / language / e2e)
docs/        design docs (see index below)
```

## Development Conventions

1. **No language knowledge in the engine.** The engine must not hardcode any
   token name / rule name / structural category. Language knowledge is always
   TOML declarations + rule derivation. Before touching the engine, ask: can
   this be expressed as config / a rule field instead?
2. **Tests before code.** Every functional change ships with tests; bug fixes
   start with a failing test case.
3. **TODO lists only unfinished work.** Completed history lives in git log +
   the test suite, not in TODO.
4. **Commit messages:** `[feature] description` prefix + change summary +
   verification result (test count / coverage).

## Documentation Index

| Doc | Content |
|---|---|
| docs/language_walkthrough.md | Step-by-step guide to building a language from scratch (c4 as example) |
| docs/config_lifecycle.md | Config lifecycle (declare_cfg timing / pitfalls) |
| docs/expression_conventions.md | Expression implicit conventions (Pratt / precedence) |
| docs/component_protocol.md | Plugin-layer protocol (components / slots / primitives) |
| docs/grammar_rule_fields.md | Grammar rule field reference |
| docs/coding_style.md | Code style |
| docs/decisions/ | ADRs (architecture decision records) |

> **Doc alignment note:** the project maintains a bidirectional doc-code index
> (`MODEL_INDEX.md` + `Doc:` / `Impl:` markers) optimized for model-assisted
> maintenance. Core maintainers keep it in sync; **external PRs are not
> required to** — a code change without index updates is fine, maintainers will
> reconcile.

## Testing Guidelines

- New features: add a test file under `tests/<module>/`.
- Language-pack changes: run `pytest tests -q --cov` to confirm the gate (>= 84%).
- e2e: `tests/e2e/` (pipeline / macro reverse / fidelity / enhanced render).
- Idempotency: formatter changes must pass `tests/formatter/test_idempotent.py`.
