# TransParadigm — configuration-driven language pipeline

<!--
Keywords: TOML grammar; configuration-driven pipeline; recursive descent + Pratt;
Wadler-Lindig; Doc IR; Verilog; pretty printer; linter; preprocessor; Python;
compiler frontend; context-sensitive grammar; language workbench; DSL extension;
model-friendly configuration; forkable pipeline
-->

![version](https://img.shields.io/badge/version-0.1.0-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.11%2B-orange)
![status](https://img.shields.io/badge/status-experimental-yellow)

**Write language rules in TOML — the engine is a generic, forkable pipeline.**
Lexer, parser, and a pre-parse linter are fully configuration-driven; analyzer
and transform are plugin extension points; the renderer formats via
config-declared layouts. Adding a language (or extending one) is writing TOML
plus optional plugin scripts — no engine code.

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
    impl spi.master (.clk(clk)) => spi_io;
endmodule
```

Run the pipeline and `type spi { ... }` expands to standard Verilog:

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

## Table of contents

- [Why / when not to use](#why--when-not-to-use)
- [Quick start](#quick-start)
- [Example: a Verilog type extension](#example-a-verilog-type-extension)
- [Second language: c4](#second-language-c4)
- [Language rules in TOML](#language-rules-in-toml)
- [Documentation](#documentation)
- [Project structure](#project-structure)
- [Verification](#verification)
- [Contributing](#contributing)
- [Status](#status)
- [Known limitations](#known-limitations)
- [License](#license)

## Why / when not to use

TransParadigm is for building **forkable, model-friendly language toolchains**
where the language itself stays as data:

- **Rules are data, not code.** All language specifics live in TOML config
  files. The engine is a generic skeleton; every stage has a configuration
  surface.
- **Forkable, not rewrite.** Each stage can be replaced or reconfigured. Fork
  the repo to make private, incremental changes to *your* language pipeline —
  no engine rewrite required.
- **Domain-DSL evolution.** Add abstractions on top of an existing language
  (e.g. a custom type system on Verilog) — no second compiler, just extend the
  pipeline you already have.
- **Model-friendly.** Onboarding is optimized for model-assisted contributors:
  entry-point index, verification protocol, known landmines. The c4 language
  pack was written as TOML grammar + plugin scripts (by a model) and compiles
  to c4 VM assembly.
- **Pre-parse token linter.** The linter runs *before* the parser on the raw
  token stream — not an AST. It reuses the same TOML grammar and part of the
  parser machinery, so syntax knowledge never drifts between lint and parse,
  and it can check broken code that would fail AST construction.
- **Sliceable — take only what you need.** The pipeline is stage-separated:
  `format`, `lint`, `expand`, and the full pipeline are independently usable.
  Grab one capability without learning the rest — no need to understand the
  whole pipeline to use a slice. Slicing is self-service: the pipeline is
  maintained whole, and how you use your slice is up to you.

**When not to use:** TransParadigm is one way to build a language toolchain,
not a replacement for general-purpose parser generators. If you just need a
parser for a one-off grammar, [ANTLR](https://www.antlr.org/) or Yacc are
excellent tools — use them. This project targets a different niche: a
forkable, model-friendly pipeline for DSLs, subsets, and custom extensions.
It is also **not a behavioral verifier** — it checks well-formedness against
your rules, but does not simulate, synthesize, or prove hardware correctness.

## Quick start

Requirements: Python 3.11+ (zero runtime dependencies).

> **Not yet on PyPI** — install from source. See [Status](#status).

```bash
git clone <this-repo> && cd tpc_compiler
pip install -e ".[test]"     # editable install + test deps

tpc --version                # 0.1.0
tpc format input.v           # format a Verilog file (stdout)
tpc lint input.v             # pre-parse token lint (exit 1 on diagnostics)
tpc lint input.v --json      # LSP-compatible JSON diagnostics
tpc expand input.v           # expand macros + transform (per [commands].expand)
tpc config dump              # show every config key's source (file + section)
tpc new component my_feature --lang verilog   # scaffold a plugin component
```

`tpc config dump` is the debugging entry point for "where does this config
value come from" — it resolves the language pack and prints each key's source
file and section (also available as `--json`).

Style entry points:

- **Project defaults** — `config/tpc_config.json` (pipeline stage toggles,
  `format_output`, macro `define`/`undefine`, include dirs).
- **Language pack style** — `[formatter.style]` in
  `grammar/<lang>/base/_style.toml` (`indent_width`, `max_line_width`, …).
- **Where does this config value come from?** — `tpc config dump`.

Python API reference in [docs/api.md](./docs/api.md).

## Example: a Verilog type extension

The pipeline takes `type` / `type.role` / `impl` (enhanced syntax) and expands
it to plain Verilog — a domain-DSL evolution without a second compiler.

> The pre-parse linter shares the same rule table as the parser — including
> plugin grammar — so enhanced syntax (`type` / `impl`) is linted like plain
> Verilog and the example above passes the lint gate as-is. `no_lint=True`
> exists only as an escape hatch to skip the gate; it is not required for
> enhanced syntax.

```python
from pipeline import run_pipeline_on_source

with open("top.v") as f:
    src = f.read()

result = run_pipeline_on_source(source=src)  # lint gate on — enhanced syntax passes it
print(result["output"])                        # expanded standard Verilog
```

`expand_enhanced=False` keeps the enhanced syntax instead — the two paths share
the same formatter; `expand_enhanced` only controls whether the enhanced AST
nodes are expanded (analyze + transform) or preserved (rendered directly by
their `[Rule.renderer.layout]`).

## Second language: c4

The same engine, a different language pack. `grammar/c4/` defines a tiny C
subset (types, expressions, statements, functions) in TOML plus one plugin
script that lowers the AST to c4 VM assembly — **no engine changes**:

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

## Language rules in TOML

**How to read this example:** language knowledge lives entirely in TOML —
`[id.keyword]` defines lexer keywords, `[Rule.parser]` defines syntax
(`@X` references another rule, `$N` captures the N-th production slot),
`[Rule.parser.node]` shapes the AST, `[Rule.renderer.layout]` controls
output. The engine is generic; nothing here is hardcoded in Python.

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
drives lexer, parser, formatter, linter, and renderer. Full walkthrough (from
zero to a working language): [docs/language_walkthrough.md](./docs/language_walkthrough.md).

## Documentation

| Document | Contents |
|----------|----------|
| [docs/README.md](./docs/README.md) | Doc navigation & alignment conventions (`Doc:`/`Impl:`/`Test:`) |
| [docs/MODEL_INDEX.md](./docs/MODEL_INDEX.md) | **Read before modifying**: knowledge-unit jump table → doc → impl → test |
| [docs/api.md](./docs/api.md) | Python API reference (stage-level components) |
| [docs/component_protocol.md](./docs/component_protocol.md) | Plugin components / slots / primitives / inject |
| [docs/linter_architecture.md](./docs/linter_architecture.md) | Pre-parse linter architecture |
| [docs/semantic_checks.md](./docs/semantic_checks.md) | Semantic check slot design (two-layer rules + post-pass) |
| [docs/known_limitations.md](./docs/known_limitations.md) | Full known-limitations list |
| [docs/e2e_real_projects.md](./docs/e2e_real_projects.md) | Real-core validation corpus |
| [docs/release_checklist.md](./docs/release_checklist.md) | Release SOP |
| [docs/language_walkthrough.md](./docs/language_walkthrough.md) | Build a language from zero (c4 as the worked example) |

## Project structure

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
plugin scripts — no engine code required to add or modify a language (see
[Language rules in TOML](#language-rules-in-toml) above).

## Verification

```bash
python -m pytest tests/ -q                # unit tests (see tests/ for count)
python tests/e2e/run_all_tests.py           # pipeline E2E + fidelity (FAIL 0)
python tests/e2e/eval_lint_accuracy.py      # linter accuracy gate (recall 100%)
```

CI ([.github/workflows/ci.yml](./.github/workflows/ci.yml)) runs the full
suite with a coverage gate plus a wheel-install smoke test, on
Python 3.11/3.12/3.13 × Windows/Ubuntu.

## Contributing

- Read [AGENTS.md](./AGENTS.md) first — project conventions and the hard
  constraints (language knowledge stays in `grammar/` data; config loading is
  fail-fast).
- Before touching a subsystem, check [docs/MODEL_INDEX.md](./docs/MODEL_INDEX.md)
  for the knowledge unit → doc → impl → test jump.
- Run the [verification gates](#verification) before submitting.
- Model-assisted contributions are welcome by design — the repo is set up so a
  contributor with a model can understand, modify, and verify the pipeline
  cheaply.

## Status

**Experimental — Alpha, not yet published to PyPI.** Version 0.1.0.

Verilog support is a synthesizable subset — not full IEEE 1364. The pipeline
is validated against real open-source cores (PicoRV32, darkriscv, SERV, TV80) —
see [docs/e2e_real_projects.md](./docs/e2e_real_projects.md).

Built with Python 3.11+, zero runtime dependencies.

## Known limitations

Honest boundaries — these are structural or deliberate, not hidden bugs.
Summary:

- **Small-to-medium languages only.** The wall for C++-scale grammars is rule
  scale and semantic depth, not context-sensitivity; TOML config cannot shrink
  engineering volume. Implementing a well-chosen subset is the recommended
  path for large languages.
- **Not a behavioral verifier.** Checks well-formedness against your rules —
  no simulation, synthesis, or elaboration; not a correctness prover.
- **No SystemVerilog; Verilog-2001 is itself a subset** (no gate primitives,
  UDP, `specify`, `config`/`defparam`, procedural `assign`/`deassign`).
- **Single-source processing — no design elaboration**: no cross-module
  instance graph, no hierarchical names, no elaboration-time generate.
- **No IDE / LSP; no incremental parsing; interpreter-bound throughput**
  (~19k tok/s combined; fine for single files and small/medium projects).
- **Deep semantics live in plugin code, not TOML** — config drives syntax,
  rendering, and shallow semantics; genuinely new semantic capabilities are
  engine primitives / plugin scripts.

Full list (correctness boundaries, architecture boundaries, engineering
frictions): [docs/known_limitations.md](./docs/known_limitations.md).

## License

MIT — see [LICENSE](./LICENSE). Fork and adapt freely; private modifications allowed.

## README provenance

This README was written with model assistance. The descriptions of the
pipeline, its stages, and their extensibility are accurate as of the latest
revision, but if you find any statement that does not match the actual code,
please open an issue with a correction — precise documentation is preferred
over polished claims.

[Design docs](./docs/) · [Known limitations](./docs/known_limitations.md)
