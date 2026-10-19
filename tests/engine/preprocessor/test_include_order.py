"""include 内容行顺序（A2 末片，循环 #25）。

判据：`#include` 指令行的 marker 必须**先于**被包含内容（含被包含文件里
`#define` 的 marker）；条件分支内的 include 与其内容必须**同归属**（都在该
分支），否则 clean 行序 / 行映射 / 渲染回插顺序错位。

生产同路：`preprocessor._expand.scan_directives`（`pipeline._stage_macro_scan`
同一入口）。改前红：内容行出现在 include marker 之前。
"""
from preprocessor._expand import scan_directives

PACK = "grammar/c"


def _scan(tmp_path, src: str, header: str):
    (tmp_path / "h.h").write_text(header, encoding="utf8")
    (tmp_path / "main.c").write_text(src, encoding="utf8")
    return scan_directives(
        src,
        PACK,
        source_path=str(tmp_path / "main.c"),
        search_dirs=[str(tmp_path)],
    )


def _line_of_marker(lines: list[str], placeholders: dict, text_prefix: str) -> int:
    marker = next(k for k, v in placeholders.items() if v.startswith(text_prefix))
    return next(i for i, line in enumerate(lines) if marker in line)


def test_include_marker_precedes_header_content_and_child_directive(tmp_path):
    """顶层：include marker < 头文件内容 < 头文件 `#define` marker。"""
    *_, placeholders, _directive_lines, clean, clean_to_raw = _scan(
        tmp_path,
        '#include "h.h"\nT x;\n',
        "int hdr_var;\n#define T int\n",
    )
    lines = clean.split("\n")

    include_idx = _line_of_marker(lines, placeholders, '#include "h.h"')
    define_idx = _line_of_marker(lines, placeholders, "#define T int")
    content_idx = lines.index("int hdr_var;")

    assert include_idx < content_idx, clean
    assert content_idx < define_idx, clean
    # 指令行 marker 仍映射回宿主 include 行；被包含内容行不可映射（None）
    assert clean_to_raw[include_idx] == 1
    assert clean_to_raw[content_idx] is None


def test_include_inside_active_branch_keeps_marker_and_content_in_branch(tmp_path):
    """条件分支内：include marker 与内容都归该分支，且 marker 在前。"""
    *_, placeholders, _directive_lines, clean, _map = _scan(
        tmp_path,
        "#define ON 1\n#ifdef ON\n#include \"h.h\"\n#endif\nint y;\n",
        "int hdr;\n",
    )
    lines = clean.split("\n")

    include_idx = _line_of_marker(lines, placeholders, '#include "h.h"')
    content_idx = lines.index("int hdr;")
    assert include_idx < content_idx, clean

    # 内容行必须落在 include marker 之后、`int y;` 之前（即仍在分支 flush 段内）
    assert include_idx < content_idx < lines.index("int y;"), clean
