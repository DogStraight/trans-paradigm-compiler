# PyV — configuration-driven compiler frontend

<!--
Keywords: TOML grammar; configuration-driven parser; recursive descent + Pratt;
Wadler-Lindig; Doc IR; Verilog; pretty printer; Python; compiler frontend;
context-sensitive grammar; metaprogramming; language workbench;
AI-friendly configuration
-->

Write grammar rules in TOML. Parse and format any language with the same config.

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

## Quick start

```bash
pip install pyv-compiler
pyv format input.v              # format Verilog
pyv expand input.v              # expand type extensions
```

## How it works

Rules are data, not code. All language specifics live in TOML config files. The engine is generic.

```
Source -> preprocessor -> Lexer -> Parser -> Analyze -> Transform -> Renderer -> Output
```

Swap config directory = change language. No engine changes.

## Status

- [x] Verilog core subset (module, always, if/case/for, function/task, expressions, instances)
- [x] Custom type extensions (`type spi { master/slave }` -> port expansion)
- [x] Formatter with Wadler-Lindig Doc IR pretty printing
- [ ] Error-tolerant formatting mode
- [ ] Preprocessor (`` `include `` / `define` / `ifdef`)
- [ ] More language configs

Built with Python 3.11+, zero external dependencies.

[ROADMAP](./ROADMAP.md) | [Design docs](./docs/)
