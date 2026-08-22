# TransParadigm — configuration-driven language pipeline

<!--
Keywords: TOML grammar; configuration-driven pipeline; recursive descent + Pratt;
Wadler-Lindig; Doc IR; Verilog; pretty printer; linter; preprocessor; Python;
compiler frontend; context-sensitive grammar; language workbench; DSL extension;
model-friendly configuration; forkable pipeline
-->

Write language rules in TOML. The front of the pipeline — lexer, parser,
linter — is fully configuration-driven; analyzer and transform are pure
plugin extension points, while the renderer is semi-closed (layout is
configurable, but only its primitives are extensible). The whole pipeline
is forkable and model-friendly (at least, that is the goal — see Status and
Known limitations below).

## Project features

> TransParadigm is one way to build a language toolchain — not a replacement
> for general-purpose parser generators like ANTLR or Yacc. If you just need a
> parser for a one-off grammar, those are excellent tools. This project targets
> a different niche: a forkable, model-friendly pipeline where language rules
> stay as data and every stage stays reachable for incremental changes. Use it
> when that trade-off fits; otherwise ANTLR/Yacc remain perfectly good choices.

- **Rules are data, not code.** All language specifics live in TOML config files.
  The engine is a generic skeleton; every stage has a configuration surface.
- **Forkable, not rewrite.** Each stage can be replaced or reconfigured. Fork
  the repo to make private, incremental changes to *your* language pipeline —
  no engine rewrite required.
- **Domain-DSL evolution.** Add abstractions on top of an existing language
  (e.g. a custom type system on Verilog) — no second compiler, just extend the
  pipeline you already have.
- **Model-friendly.** Onboarding is optimized for model-assisted contributors:
  entry-point index, verification protocol, known landmines. A contributor with
  a model can understand, modify, and verify the pipeline cheaply.
  The c4 language pack was written as TOML grammar + plugin scripts (by a
  model) and compiles to c4 VM assembly.
- **Pre-parse token linter.** The linter runs *before* the parser and consumes
  the raw token stream — not an AST. It reuses the same TOML grammar and part of
  the parser machinery (Pratt + shared RuleMatcher), so syntax knowledge never
  drifts between lint and parse, and it can check broken code that would fail
  AST construction.

```verilog
// Define a custom type with roles, then use it in a module port
type spi {
    master : input sclk, input miso, output mosi, output cs;
    slave  : invert master;   // slave = master with port directions reversed
}

module top(
    input clk,
    spi.slave spi_io
);
    // impl type.role (...) => iface binds an interface instance:
    // explicitly connected ports are kept (.clk), the rest are
    // auto-connected to the interface expansion signals (spi_io_*)
    impl spi.master (.clk(clk)) => spi_io;
endmodule
```

Running the pipeline expands the custom type to standard Verilog. The
interface port `spi.slave spi_io` is expanded to concrete ports, and the
`impl` binding is rewritten to a module instantiation whose unlisted ports
are auto-connected to the interface signals:

```verilog
module top(
    input    clk,
    output   spi_io_sclk,
    output   spi_io_miso,
    input    spi_io_mosi,
    input    spi_io_cs
);

    spi_master u_spi_master_acb99d (
        .clk (clk        ),
        .sclk(spi_io_sclk),
        .miso(spi_io_miso),
        .mosi(spi_io_mosi),
        .cs  (spi_io_cs  )
    );

endmodule
```

> `impl[master](...)` inside the `type` body can carry the implementation
> body; the pipeline emits it as a separate wrapper module file (e.g.
> `spi_master.v`).

### Running the example

Expansion is the default pipeline behavior (`expand_enhanced=True`). Save the
input above to `top.v`, then run it through the pipeline:

```python
from pipeline import run_pipeline_on_source

with open("top.v") as f:
    src = f.read()

result = run_pipeline_on_source(source=src, no_lint=True)  # expand_enhanced=True by default
print(result["output"])                        # expanded standard Verilog
```

> `no_lint=True` is required for enhanced syntax today: the pre-parse linter
> targets plain Verilog and does not yet know `type` / `spi.slave` / `impl`
> tokens, so it would reject the input before parsing. Enhanced constructs run
> through the full pipeline (parse → analyze → transform → render) but skip the
> token-level lint gate.

To keep the enhanced syntax instead (format the `type spi { ... }` as-is):

```python
result = run_pipeline_on_source(source=src, no_lint=True, expand_enhanced=False)
```

The two paths share the same formatter; `expand_enhanced` only controls
whether the enhanced AST nodes are expanded (analyze + transform) or preserved
(rendered directly by their `[Rule.renderer.layout]`).

## Quick start

```bash
pip install -e ".[test]"     # editable install + test deps (zero runtime deps)

tpc --version                # 0.1.0
tpc format input.v           # format a Verilog file (stdout)
tpc lint input.v             # pre-parse token lint (exit 1 on diagnostics)
tpc lint input.v --json      # LSP-compatible JSON diagnostics
```

Style entry points:
- **Project defaults** — `config/tpc_config.json` (pipeline stage toggles,
  `format_output`, macro `define`/`undefine`, include dirs).
- **Language pack style** — `[formatter.style]` in `grammar/<lang>/base/_style.toml`
  (`indent_width`, `max_line_width`, …).
- **Where does this config value come from?** — `tpc config dump`.

Full command reference below; Python API reference in [docs/api.md](./docs/api.md).

## Command-line usage

The `tpc` CLI drives the pipeline per the language pack's `[commands]`
declarations:

```bash
tpc format input.v          # format a Verilog file (per [commands].format)
tpc lint input.v            # pre-parse token lint (exit 1 on diagnostics)
tpc lint input.v --json     # LSP-compatible JSON diagnostics
tpc expand input.v          # expand macros + transform (per [commands].expand)
tpc config dump             # show every config key's source (file + section)
tpc new component my_feature --lang verilog   # scaffold a plugin component
```

`tpc config dump` is the debugging entry point for "where does this config
value come from" — it resolves the language pack and prints each key's source
file and section (also available as `--json`).

## How it works

Rules are data, not code. All language specifics live in TOML config files. The engine is generic.

```
Source -> preprocessor -> Lexer -> Parser -> Analyze -> Transform -> Renderer -> Output
```

Each stage is independently configurable: swap a config directory, replace a
production, inject a transform plugin — the rest of the pipeline stays intact.

## Pipeline stages

Each stage consumes the previous stage's output. The same small module runs
through every stage below:

```verilog
module m(input clk);
    reg a;
    always @(posedge clk) a <= 1;
endmodule
```

### Preprocessor — source → expanded source

Macro directives are config-declared (`base/_macro.toml`): directive
recognition, expansion, and reverse mapping back to the original text.
The module above has no macros, so it passes through unchanged; a module
with macros is expanded to plain text for parsing, then the original
directives are restored in the output — so formatted/linted output keeps
the `define`/`ifdef` structure intact.

### Lexer — source → token stream

Token types are config-declared (`[id.keyword]`, `[symbol]`, `[bracket]` in
`base/_token.toml`); the lexer is a generic scanner over that table.

```
keyword.module 'module'  id 'm'  bracket.l_parentheses '('  keyword.input 'input'
id 'clk'  bracket.r_parentheses ')'  symbol.base.semicolon ';'  newline '\n'
keyword.reg 'reg'  id 'a'  symbol.base.semicolon ';'  newline '\n'
keyword.always 'always'  symbol.base.at '@'  bracket.l_parentheses '('
keyword.posedge 'posedge'  id 'clk'  bracket.r_parentheses ')'  id 'a'
symbol.extend.lesser_equal '<='  literal.number '1'  symbol.base.semicolon ';'
newline '\n'  keyword.endmodule 'endmodule'
```

### Parser — token stream → AST

Rules reference tokens and other rules (`@Expression`, `@Stmt`); the parser
is recursive descent + Pratt over the rule table.

```
Root
  ModuleDecl
    RegDecl
    AlwaysStmt
```

### Linter — source → diagnostics

Runs *before* the parser on the raw token stream. A missing semicolon:

```verilog
module m(input clk);
    reg a
    always @(posedge clk) a <= 1;
endmodule
```

produces:

```
[phase-statement] expected 'symbol.base.semicolon', got 'keyword.always'
```

### Analyzer — AST → scopes & symbols

Walks the AST, builds a scope tree and symbol table (config-declared
`[Rule.analyzer.scope]` / `[Rule.analyzer.symbol]`), and reports semantic
diagnostics. For the module above it registers the module symbol in the
global scope:

```
root_scope: <global> / global
symbols:   [{'name': 'm', 'kind': 'module', 'scope': '<global>', 'scope_kind': 'global'}]
diagnostics: []
```

### Transform — AST → transformed AST

Config-driven structural rewrites (e.g. typed_ports expansion, macro
handling). The typed_ports example above shows the input/output: `type spi`
+ `impl` binding → standard module instantiation.

### Renderer — AST → text

Doc IR layout is config-declared (`[Rule.renderer.layout]`); the renderer
walks the AST and emits formatted text. The formatter (indent, alignment,
wrap) runs on the rendered output:

```verilog
module m(input clk);
    reg a;
    always @(posedge clk) a <= 1;
endmodule
```

## Subsystems

| Directory | Role |
|-----------|------|
| `grammar/` | Language rules as data — `verilog/` and `c4/` TOML packs |
| `lexer/` | Lexing: token-definition-driven scanning |
| `parser/` | Syntax: recursive descent + Pratt + rule selection |
| `linter/` | Pre-parse, token-level lint (reverse parser, reuses the same TOML grammar) |
| `preprocessor/` | Macro expansion / reverse mapping |
| `analyzer/` | Semantic analysis: scopes, symbols, types (extensible primitives) |
| `transform/` | Semantic mapping + config-driven transformations |
| `renderer/` | Doc IR → formatted output (Wadler-Lindig) |
| `core/` | Engine skeleton: config registry, errors, plugin loading |

A language pack is a set of TOML files under `grammar/<lang>/` plus optional
plugin scripts — no engine code required to add or modify a language.

## Language rules in TOML

Concrete example from the c4 language pack (`grammar/c4/`) — a tiny C subset:

> **How to read this example:** language knowledge lives entirely in TOML —
> `[id.keyword]` defines lexer keywords, `[Rule.parser]` defines syntax
> (`@X` references another rule, `$N` captures the N-th production slot),
> `[Rule.parser.node]` shapes the AST, `[Rule.renderer.layout]` controls
> output. The engine is generic; nothing here is hardcoded in Python.

```toml
# token.toml — keywords (lexer turns them into keyword.* tokens)
[id.keyword]
if = "if"
else = "else"
while = "while"
int = "int"
return = "return"

# 01_statement.toml — a statement rule: production + AST shape
[IfStmt]
is_statement = true

[IfStmt.parser]
production = [
    "keyword.if",
    "bracket.l_parentheses",
    "@Expression",
    "bracket.r_parentheses",
    "@Stmt",
    "(keyword.else,@Stmt)?",
]

[IfStmt.parser.node]
cond = "$3"
then_body = "$5"
else_body = "$6"

# 00_expression.toml — an atom + how it renders
[Number.parser]
is_atom = true
production = ["literal.number"]

[Number.parser.node]
value = "$1"

[Number.renderer.layout]
ref = "value"
```

Rules reference tokens (`keyword.if`, `literal.number`), other rules
(`@Expression`, `@Stmt`), and positional captures (`$3`) — the same notation
drives lexer, parser, formatter, linter, and renderer. Operators, precedence,
and rendering live in the same pack (`base/_symbol_level.toml` for Pratt
priority, `[Rule.renderer.layout]` for Doc IR layout).

## Second language: c4

The same engine, a different language pack. `grammar/c4/` defines a tiny C
subset (types, expressions, statements, functions) in TOML plus one plugin
script that lowers the AST to c4 VM assembly — no engine changes:

```c
int main() { int x; x = 1; return x; }
```

compiles to c4 VM assembly (LEA/IMM/JMP/ADD/... opcodes):

```asm
ENT  0
LEA  0
PSH
IMM  1
SI
LEA  0
LI
LEV
LEV
```

The c4 pack is TOML + one plugin script; the engine code is shared with the
Verilog pack (no c4-specific branches in `core/`/`lexer/`/`parser/`).

## Status

Verilog support is currently a synthesizable subset — not full IEEE 1364.
The pipeline is validated against real open-source cores (PicoRV32, darkriscv,
SERV, TV80) — see [docs/e2e_real_projects.md](./docs/e2e_real_projects.md).

Built with Python 3.11+, zero runtime dependencies.

## Known limitations

Honest boundaries — these are structural or deliberate, not hidden bugs.

### Scope & config complexity

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
  emit, renderer layout), each with its own implicit conventions. The README
  example only shows the syntax surface. Entry points for secondary
  development: `docs/MODEL_INDEX.md` (jump table) and
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

### Correctness boundaries

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

### Architecture boundaries

- **Parser is classic recursive descent + Pratt (LL-style)** — not LR/GLR, and
  there is no parser-level error recovery (no skip-to-sync-point and
  continue). Syntax errors are caught by the pre-parse linter and block the
  pipeline; the parser only has soft-failure detection (`_parse_truncated`).
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

### Engineering frictions (usage & secondary development)

- Enhanced syntax (`type` / `type.role` / `impl`) currently requires
  `no_lint=True`: the pre-parse linter targets plain Verilog and does not know
  the enhanced tokens, so it would reject the input before parsing.
- **`invert` over a role that itself carries nested/ref ports is only
  partially expanded** (`type wrap { master : spi.master inner, input enable;
  slave : invert master; }`): the inverted role's nested-expanded ports
  (`inner_*`) do not participate in the direction inversion — only its plain
  ports do (`enable`). The pipeline defends against leaking literal `SKIP`
  into the port list (empty rows are filtered from the mapping table and
  no-output results are dropped at expand), so output is valid Verilog with the
  nested-inverted ports silently missing rather than corrupt output. Full
  expansion needs the inverted role's *merged* port set (plain + refs) at
  resolve time; tracked in `TODO.md` P1.5.
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

## Python API

The pipeline entry point is `run_pipeline_on_source` (shared by the CLI and the
test suite). Minimal embed:

```python
from pipeline import run_pipeline_on_source

result = run_pipeline_on_source(
    source=verilog_src,
    quiet=True,
    no_lint=True,            # enhanced syntax (type/impl) skips the lint gate today
    expand_enhanced=True,    # False keeps the enhanced syntax instead of expanding
)
print(result["output"])      # rendered / expanded Verilog
print(result["success"], result.get("error", ""))
```

Stage-level components (`Lexer` / `Parser` / `AnalysisTraversal` /
`AstTransformer` / `Renderer` / `LinterScanner`) and the component protocol
are documented in [docs/api.md](./docs/api.md) and
[docs/component_protocol.md](./docs/component_protocol.md).

## Verification

```bash
python -m pytest tests/ -q                # unit tests (see tests/ for count)
python tests/e2e/run_all_tests.py           # pipeline E2E + fidelity (FAIL 0)
python tests/e2e/eval_lint_accuracy.py      # linter accuracy gate (recall 100%)
```

## README provenance

This README was written with model assistance. The descriptions of the
pipeline, its stages, and their extensibility are accurate as of the latest
revision, but if you find any statement that does not match the actual code,
please open an issue with a correction — precise documentation is preferred
over polished claims.

## License

MIT — see [LICENSE](./LICENSE). Fork and adapt freely; private modifications allowed.

[Design docs](./docs/) | [Linter architecture](./docs/linter_architecture.md)
