# PyV — configuration-driven compiler frontend

<!--
Keywords: TOML grammar; configuration-driven parser; recursive descent + Pratt;
Wadler-Lindig; Doc IR; Verilog; pretty printer; Python; compiler frontend;
context-sensitive grammar; metaprogramming; language workbench;
AI-friendly configuration
-->

Write grammar rules in TOML. Parse and format any language with the same config.

```verilog
// Input: Verilog with custom type extensions
module spi_invoker (
    input  wire         clk,
    spi.slave           spi_io,
    output reg  [7:0]   spi_data
);
```

&#x2193; *one command*

```verilog
// Output: formatted standard Verilog
module spi_invoker (
    input  wire              clk,
    input  logic [7:0]       spi_io_data_in,
    input  logic [7:0]       spi_io_addr,
    output reg   [7:0]       spi_data
);
```

## Quick start

```bash
pip install pyv-compiler
pyv format input.v              # format Verilog
pyv expand input.v              # expand type extensions
```

## How it works

Rules are data, not code. The engine reads TOML, parses and renders. All language specifics live in config.

```
engine:  preprocess &#x2192; pre_scan &#x2192; lexer &#x2192; parser &#x2192; normalize &#x2192; analyze &#x2192; transform &#x2192; render
config:  _preprocess  pre_scan  _token  rules_   normalize  scope +  transform  layout
         .toml        .toml     .toml   *.toml   .toml      symbol    *.toml     .toml
```

Switch language = swap config files. No engine changes.

## Status

- &#x2705; Verilog core subset (module, always, if/case/for, function/task, expressions, instances)
- &#x2705; Custom type extensions (`type spi { master/slave }` &#x2192; port expansion)
- &#x2705; Formatter with Wadler-Lindig Doc IR pretty printing
- &#x23F1;&#xFE0E; Error-tolerant formatting mode
- &#x23F1;&#xFE0E; Preprocessor (`` `include `` / `define` / `ifdef`)
- &#x23F1;&#xFE0E; More language configs

Built with Python 3.11+, zero external dependencies.

[ROADMAP](./ROADMAP.md) | [Design docs](./docs/)
