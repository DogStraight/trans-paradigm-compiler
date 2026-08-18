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

## Command-line usage

Install (editable + test deps):

```bash
pip install -e ".[test]"
```

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

## Preprocessor

Verilog macro handling is config-declared (`base/_macro.toml`): directive
recognition, expansion, and reverse mapping back to the original text:

```verilog
`define WIDTH 8
`ifdef WIDTH
    reg [`WIDTH-1:0] data;
`else
    reg [7:0] data;
`endif
```

The pipeline expands macros and conditional blocks, then restores the
original directives in the output — so formatted/linted output keeps the
`define`/`ifdef` structure intact.

## Status

- [x] Verilog core subset (module, always, if/case/for, function/task, expressions, instances)
- [x] Configurable pipeline — lexer / parser / analyze / transform / render
- [x] Custom type extensions (typed_ports: `type spi { master/slave }` -> port expansion)
- [x] Formatter with Wadler-Lindig Doc IR pretty printing
- [x] Linter — pre-parse, token-level "reverse parser"; shares grammar & parser infra (31/31 recall, 0 FP)
- [x] Preprocessor (`` `include `` / `define` / `ifdef` / `undef`)
- [x] Second-language validation — c4 (tiny C) built from TOML + plugin, compiles to VM assembly
- [x] Model guide artifacts (AGENTS.md + docs/MODEL_INDEX.md)
- [x] Packaging / CI (pip install, GitHub Actions on 3.11/3.12/3.13)
- [ ] Error-tolerant formatting mode

Built with Python 3.11+, zero runtime dependencies.

## Known limitations

- **The complexity wall.** Configuration-driven grammar is a sweet spot for
  small-to-medium languages (DSLs, subsets, custom extensions — the c4 and
  Verilog-core cases). For large, complex languages (think C++-scale grammar),
  the wall is not context-sensitivity — the parser resolves `a * b` as a
  pointer declaration vs. a multiplication via a symbol table
  (`pre_symbols` + scope lookup + per-kind rule hints, all config-declared).
  The wall is *rule scale and semantic depth*: hundreds of productions,
  template instantiation, overload resolution, elaborate type systems — those
  are engineering volume that TOML config cannot shrink, and they are not
  what this tool is aimed at. C++/Rust-scale grammars are out of scope.
- **Verilog coverage is a subset**, not full IEEE 1364. Focus: synthesizable core
  (module/always/if/case/for/function/task/instances) + custom type extensions.
- **No IDE / LSP** — this is a CLI pipeline, not an editor plugin.
- **No optimization passes** — transforms are config-driven structural rewrites
  (e.g. type expansion, macro handling), not LLVM-style optimization.
- **Line wrapping is width-based, not semantic.** The formatter wraps
  over-long lines (>100 cols) at safe break points (top-level commas, logical/
  arithmetic operators, ternary `?`/`:`), using a penalty model (Verible-style)
  to pick the least-bad break. It does not reflow to a target width like a
  paragraph formatter — it only breaks lines that exceed the limit, and only
  at syntactically safe points.
- **Error tolerance is linter-side.** Syntax errors are caught by the pre-parse
  linter and block the pipeline. The parser has soft-failure detection
  (`_parse_truncated`) that flags incomplete parses, but there is no
  parser-level error recovery (no skipping to a sync point and continuing).

## Verification

```bash
python -m pytest tests/ -q                # 685 unit tests
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
