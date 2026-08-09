# PyV — configuration-driven language pipeline

<!--
Keywords: TOML grammar; configuration-driven pipeline; recursive descent + Pratt;
Wadler-Lindig; Doc IR; Verilog; pretty printer; linter; preprocessor; Python;
compiler frontend; context-sensitive grammar; language workbench; DSL extension;
model-friendly configuration; forkable pipeline
-->

Write language rules in TOML. The whole pipeline — lexer, parser, analyzer,
transform, renderer — is configurable, forkable, and model-friendly.

## Why PyV

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
- **Pre-parse token linter.** The linter runs *before* the parser and consumes
  the raw token stream — not an AST. It reuses the same TOML grammar and part of
  the parser machinery (Pratt + shared RuleMatcher), so syntax knowledge never
  drifts between lint and parse, and it can check broken code that would fail
  AST construction.

```verilog
// Define a custom type with roles
type spi (parameter DATA_WIDTH = 8) {
    master : output reg [DATA_WIDTH-1:0] data_out;
    slave  : input  reg [DATA_WIDTH-1:0] data_in;
}

// Use it in a module port
module spi_invoker (
    input  wire         clk,
    spi.slave           spi_io,
    output reg  [7:0]   spi_data
);
```

-> one command

```verilog
// Expanded to standard Verilog
module spi_invoker (
    input wire clk,
    input reg [7:0] spi_io_data_in,
    output reg [7:0] spi_data
);
```

## Quick start (dev mode)

```bash
python main.py format input.v   # format Verilog
python main.py lint input.v     # lint Verilog
python main.py new component x  # scaffold a new component / plugin
```

## How it works

Rules are data, not code. All language specifics live in TOML config files. The engine is generic.

```
Source -> preprocessor -> Lexer -> Parser -> Analyze -> Transform -> Renderer -> Output
```

Each stage is independently configurable: swap a config directory, replace a
production, inject a transform plugin — the rest of the pipeline stays intact.

## Status

- [x] Verilog core subset (module, always, if/case/for, function/task, expressions, instances)
- [x] Configurable pipeline — lexer / parser / analyze / transform / render
- [x] Custom type extensions (typed_ports: `type spi { master/slave }` -> port expansion)
- [x] Formatter with Wadler-Lindig Doc IR pretty printing
- [x] Linter — pre-parse, token-level "reverse parser"; shares grammar & parser infra (31/31 recall, 0 FP)
- [x] Preprocessor (`` `include `` / `define` / `ifdef` / `undef`)
- [ ] Error-tolerant formatting mode
- [ ] Second-language validation (a minimal DSL proves the "forkable" claim)
- [ ] Model guide artifact (MODEL_GUIDE.md)
- [ ] Packaging / CI

Built with Python 3.11+, zero runtime dependencies.

## Verification

```bash
python -m pytest tests/ -q                # 329 unit tests
python verilog/run_all_tests.py           # pipeline E2E + fidelity (FAIL 0)
python verilog/eval_lint_accuracy.py      # linter accuracy gate (recall 100%)
```

## License

MIT — see [LICENSE](./LICENSE). Fork and adapt freely; private modifications allowed.

[Design docs](./docs/) | [Linter architecture](./docs/linter_architecture.md)
