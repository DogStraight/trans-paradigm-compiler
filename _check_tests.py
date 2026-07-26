"""Check which dev test files are compatible with feature branch."""
import subprocess, os

def exists(imp):
    parts = imp.split(".")
    # Try as file
    fpath = "/".join(parts) + ".py"
    if os.path.isfile(fpath):
        return True
    # Try as package/module
    for i in range(len(parts), 0, -1):
        pkg = "/".join(parts[:i])
        if os.path.isdir(pkg):
            if i == len(parts):
                return True
            sub = "/".join(parts) + ".py"
            if os.path.isfile(sub):
                return True
    return False

tests = [
    ("test_analyzer", ["analyzer.scope", "analyzer.diagnostic", "core.define"]),
    ("test_lexer", ["core.define"]),
    ("test_linter", ["linter.scanner", "core.define"]),
    ("test_linter_scanner", ["linter.scanner"]),
    ("test_parser_core", ["core.define", "parser.parser_core"]),
    ("test_pratt_parser", ["core.define", "parser.pratt_parser"]),
    ("test_preprocessor", ["preprocessor._expand"]),
    ("test_production_engine", ["core.define", "parser.parser_core", "parser._production"]),
    ("test_renderer_doc", ["core.define", "renderer.doc"]),
    ("test_renderer_primitives", ["core.define", "renderer.doc", "renderer.primitives"]),
    ("test_transform", ["core.define", "transform.normalizer", "transform.primitives.node", "transform.engine"]),
    ("test_always_sensitivity", ["core.define", "parser"]),
    ("test_coverage_boost", ["preprocessor._reverse", "renderer.postproc"]),
]

print(f"{'Test':30s} {'Deps':40s} {'Status'}")
print("-" * 80)
for name, deps in tests:
    results = []
    for d in deps:
        ok = exists(d)
        results.append(f"{d}({'Y' if ok else 'N'})")
    status = "OK" if all(exists(d) for d in deps) else "MISSING"
    print(f"{name:30s} {' '.join(results):40s} {status}")
