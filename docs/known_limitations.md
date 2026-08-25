# Known limitations — 完整版

> README 的 [Known limitations](../README.md#known-limitations) 是此文件的摘要版。
> 这里是完整边界清单。**诚实边界——这些是结构性或刻意为之的，不是隐藏的 bug。**

## Scope & config complexity

- **Small-to-medium languages only.** Configuration-driven grammar is a sweet
  spot for DSLs, subsets, and custom extensions (c4, the Verilog core). For
  C++-scale grammars the wall is not context-sensitivity — the parser resolves
  `a * b` as a declaration vs. a multiplication via a symbol table
  (`pre_symbols` + scope lookup + per-kind rule hints, all config-declared).
  The wall is *rule scale and semantic depth*: hundreds of productions,
  template instantiation, overload resolution, elaborate type systems — those
  are engineering volume that TOML config cannot shrink, and they are not what
  this tool is aimed at. **For a large target language, implementing a
  well-chosen subset is the recommended path** — the Verilog pack itself is a
  synthesizable subset, with simulation constructs moved to a plugin.
  Writing *and verifying* a full large-language pack is disproportionately
  expensive (the grammar is only half the cost; the test/e2e corpus and
  fidelity baselines are the other half).
- **Config has a learning curve.** A grammar pack spans five config surfaces
  (syntax productions, node-binding `$N` addressing, analyzer hooks, transform
  emit, renderer layout), each with its own implicit conventions. Entry points
  for secondary development: `docs/MODEL_INDEX.md` (jump table) and
  `docs/component_protocol.md` (components/slots/primitives/inject).
- **Not a behavioral verifier.** The pipeline checks well-formedness against
  your rules (syntax, structure, naming) — it does not simulate, synthesize,
  or elaborate the design, and it cannot tell you whether the hardware is
  correct. It is a front-end / spec-enforcement tool, not a correctness prover.
- **No SystemVerilog.** The pack targets a Verilog-2001 synthesizable subset.
  SV constructs (`interface`, `class`, `always_ff`/`always_comb`, assertions,
  `package`, UVM) are out of current scope. Adding SV would be a separate
  grammar pack, not an engine change.
- **Even Verilog-2001 is a subset.** Low-frequency or simulation-boundary
  constructs are omitted: gate/switch primitives (`and`/`or`/`buf`/`tran`...),
  UDP (`primitive`/`table`), `specify` blocks, `config`/`defparam`, and
  procedural `assign`/`deassign`.
- **Single-source processing — no design elaboration.** The pipeline processes
  one source (with `include` resolved), not a whole design: no cross-module
  instance graph, no hierarchical name resolution, no elaboration-time
  generate semantics.
- **Deep semantics live in plugin code, not TOML.** Config drives syntax,
  rendering, and shallow semantics (scopes/symbols/name resolution). A
  genuinely new semantic capability is an engine primitive / plugin script;
  and the expression tree shape (`UnaryOp`/`BinaryOp`) plus the built-in
  prefix operators are engine conventions a pack must align to, not fully
  free data.

## Correctness boundaries

- **Comment restoration is best-effort.** Comments are restored via anchor
  mapping. The preserve path is exact; in the expand path (macro expansion,
  transform) anchors can drift, and comments may be dropped rather than risk
  corrupting the structure — a deliberate trade-off.
- **Macro system covers common forms, not every macro kind.** Object-like and
  function-like `` `define ``, conditional compilation
  (`ifdef/ifndef/else/elsif/endif`), `` `include `` (recursive,
  cycle-detected) and backslash continuation are supported, with reverse
  mapping back to the original text. Not all kinds of "type macros" — macros
  that expand into a type/declaration shape — are supported, and compound
  nested macro calls can fail to reverse-map cleanly (the expander collapses
  them into single tokens with no word boundary for whole-word matching).
- **Linter heuristics are unavoidable.** The pre-parse linter works on broken
  code, so error recovery is a finite approximation of an open set of bad
  inputs. A few fallbacks (statement end = semicolon/line-end, container end =
  derived `_stmt_ends`, single-token-rule shape) are explicit
  "language-convention approximations" that cannot be fully derived from the
  grammar; they are annotated in the source.
- **Line wrapping is width-based, not semantic.** The formatter only breaks
  over-long lines (>100 cols) at syntactically safe points (penalty model,
  Verible-style); it does not reflow to a target width like a paragraph
  formatter.
- **Formatter preserves lines.** It re-indents, re-aligns, and breaks
  over-long lines, but never merges lines or inserts blank lines — output
  structure derives from the input's existing lines. Style is config-encoded
  and validated against reference files (fidelity baselines), not a single
  hardcoded canonical house style.
- **Idempotence is guaranteed on the preserve path only.** On the expand path
  (macro expansion / transform) content changes by design, so output is not
  idempotence-checked there.
- **Validation is sample-driven, not exhaustive.** Correctness rests on a
  curated corpus (unit tests, real cores, recall gates). There is no fuzzing,
  property-based, or differential testing against reference tools yet.

## Architecture boundaries

- **Lexer raw-capture modes: single-char delimiters, verbatim block scalars.**
  The CaptureRunner primitive (`lexer/capture_runner.py`) captures verbatim
  text until a line end, a literal marker, a full-line match, a closing
  delimiter, or a column comparison (`indent_leq` — YAML block scalars `|`/`>`
  terminate at content indentation ≤ the trigger line's). Comments, strings,
  heredocs, fenced blocks, and block scalars are config-declared
  (`[comment] pairs` legacy, `[string] delimiters`, `[[capture]]` with
  optional `after`/`next_chars` trigger conditions). Remaining gaps:
  (1) string delimiters are single-character (`"`/`'`) — multi-char
  delimiters like `"""` or Rust `r#"` need a delimiter-sequence extension;
  (2) block scalar content is captured verbatim — folding (`>`), chomping
  (`-`/`+`), and indentation indicators are preserved but not semantically
  expanded, and comments on the indicator line ride along inside the token;
  (3) trigger conditions are limited to the declarative
  prev-token-in-set + next-char-in-set pair — richer contextual predicates
  need a different mechanism.
- **Parser is classic recursive descent + Pratt (LL-style)** — not LR/GLR, and
  there is no parser-level error recovery (no skip-to-sync-point and
  continue). Syntax errors are caught by the pre-parse linter and block the
  pipeline; if malformed input slips past the linter, parser truncation now
  **also fails the pipeline** (2026-08-22, fuzz-found: truncated parse used to
  render partial output and report `success=True` — silent content loss).
- **Throughput is interpreter-bound.** Measured on a 31-file / ~5.2k-token
  corpus: lexer ~183k tok/s, parser ~21k tok/s, combined ~19k tok/s —
  50–500× slower than native compilers, the inherent cost of interpreted
  Python plus generic backtracking. Fine for single files and small/medium
  projects; not a whole-repo or very-large-file tool.
- **No IDE / LSP** — this is a CLI pipeline, not an editor plugin.
- **No optimization passes** — transforms are config-driven structural rewrites
  (e.g. type expansion, macro handling), not LLVM-style optimization.
- **No incremental parsing** — every run is a full re-parse of the source
  (incremental/re-parse is a roadmap item, not implemented).

## Engineering frictions (usage & secondary development)

- **Enhanced syntax is linted, not exempted** — and needs no `no_lint=True`:
  the pre-parse linter shares the parser's rule table, including plugin
  grammar (`setup_grammar` merges component grammar files), so valid
  `type` / `type.role` / `impl` constructs pass the lint gate (verified
  2026-08-22 across all typed_ports forms: nested refs, `invert`, type
  params, impl in module body and in type body, packed ranges). `no_lint=True`
  remains an escape hatch to skip the gate but is not required. *(Historical:
  an earlier version of this list claimed enhanced syntax required
  `no_lint=True`; that was stale — the linter has loaded plugin grammar for
  some time.)*
- **`invert` over a role that itself carries nested/ref ports is only
  partially expanded** (`type wrap { master : spi.master inner, input enable;
  slave : invert master; }`): the inverted role's nested-expanded ports
  (`inner_*`) do not participate in the direction inversion — only its plain
  ports do (`enable`). The pipeline defends against leaking literal `SKIP`
  into the port list (empty rows are filtered from the mapping table and
  no-output results are dropped at expand), so output is valid Verilog with the
  nested-inverted ports silently missing rather than corrupt output. Full
  expansion needs the inverted role's *merged* port set (plain + refs) at
  resolve time; tracked in `TODO.md` P1.5 遗留（nested+invert 组合，L2-L3 未修）。
- The `GrammarRulesRegister` rule table is a process-global singleton; loading
  two language packs in one process mixes their rules. Tests use independent
  registries, and embedding code that switches languages must do the same.
- Injecting several rules into the same target deepens propagation nesting
  (each inject wraps the target one level deeper); plugin authors should group
  injected statements under a container rule (see `plugins/sim`'s
  `SimCtrlStmt`) rather than injecting rule-by-rule.
- Transform-generated wrapper instance names carry a hash suffix (e.g.
  `u_spi_master_acb99d`); the salt is not a stable golden, so byte-exact
  comparisons of expanded output require tolerance.
- Column alignment skips multi-declarator lines
  (`reg [1:0] state, next;` is left as-is); only single-declarator lines are
  aligned.
- Width-based wrap leaves some over-long constructs unwrapped (e.g. long
  concatenations with no top-level safe break point).
- Test/coverage gate is real but not exhaustive: coverage ~83%
  (`fail_under` 80), with transform/renderer the thinnest areas.
- Language packs are not version-pinned to the engine: a pack depends on
  engine semantics (FOLLOW derivation, inject behavior, node binding). Engine
  changes are guarded by tests, not by a pack/engine version contract, so
  upgrading the engine can break an older pack.
