# Coding Style

## Language

- All docstrings, comments, and inline annotations **must be in English**.
- Module docstrings: one-line summary, then blank line, then detailed description.
- Keep descriptions concise — prefer one sentence over paragraphs.

## Documentation Style

```python
"""module_name — short description."""
```

```python
def func_name(arg: type) -> return_type:
    """Short description.

    Args:
        arg: Description.

    Returns:
        Description.
    """
```

- Use `"""` triple-quotes for docstrings.
- Inline comments use `#` with a space after `#`.
- Section separators: `# ---- Stage: name ----` (English).

## Naming

- Python: `snake_case` for functions, variables, methods.
- Node types / rule names: `PascalCase` (e.g. `Declarator`, `ModuleInst`).
- Private: `_prefix` (e.g. `_match_productions`, `_CACHE`).
- Constants: `UPPER_CASE` (e.g. `LOG_INFO`, `_ORDER_NOT_FOUND`).

## Type Annotations

- Use native syntax (Python 3.11+): `X | None`, `list[X]`, `dict[K, V]`.
- Avoid `Optional[X]`, `List[X]`, `Dict[K, V]` from `typing`.
- Only import from `typing` what has no native equivalent: `Any`, `Callable`, `ClassVar`.
