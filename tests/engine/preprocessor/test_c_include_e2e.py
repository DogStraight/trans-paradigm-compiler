"""C `#include` 端到端（A2 ②）：路径解析 / 内容进流 / 受控诊断 / 渲染不内联。

口径（`docs/gaps/gap-c-preprocessor-scope.md` ⑭）：**`path_forms` 解析生效 + 缺文件给
诊断 + 内容确实被消费进流**；渲染面只出 `#include` 原行（分析面照常消费被包含内容——
渲染前剪枝，见 `pipeline._prune_include_regions`）。

生产同路：`run_pipeline_on_source(rules_dir="grammar/c")`（与 CLI 同管线）。
"""
from pipeline import run_pipeline_on_source

PACK = "grammar/c"


def _run(src: str, tmp_path, **kw):
    """跑 C 管线（include_dirs 指到 tmp 目录；input_path 让 `""` 形态有本文件目录）。

    `input_path` 必须是**真实存在的文件**（`resolve_source_dir` 按 `isfile` 判本文件
    目录，否则回退到 rules_dir）⇒ 这里先落盘主文件。
    """
    path = tmp_path / "main.c"
    path.write_text(src, encoding="utf8")
    return run_pipeline_on_source(
        src,
        rules_dir=PACK,
        quiet=True,
        include_dirs=[str(tmp_path)],
        input_path=str(path),
        **kw,
    )


def test_quote_form_resolves_and_content_enters_stream(tmp_path):
    """`"h.h"`：内容进流（类型宏生效 ⇒ 解析通过），渲染只出 `#include` 原行。"""
    (tmp_path / "h.h").write_text("#define T int\nint hdr_var;\n", encoding="utf8")
    r = _run('#include "h.h"\nT x;\n', tmp_path)
    assert r["success"], r["error"]
    assert "#include" in r["output"]
    assert "hdr_var" not in r["output"], "头文件内容不得内联进渲染输出"


def test_angle_form_searches_include_dirs(tmp_path):
    """`<sys.h>`：只走 include_dirs（不相对本文件目录）。"""
    (tmp_path / "sys.h").write_text("#define T int\n", encoding="utf8")
    r = _run("#include <sys.h>\nT x;\n", tmp_path)
    assert r["success"], r["error"]


def test_quote_form_prefers_relative_dir(tmp_path):
    """`""` 先本文件目录：同名头两处，取**本文件目录**那份。

    判据用"解析能否通过"（冲突设计：相对版给 `T=int`，include_dirs 版给 `T=42`）。
    """
    src_dir = tmp_path / "src"
    inc_dir = tmp_path / "inc"
    src_dir.mkdir()
    inc_dir.mkdir()
    (src_dir / "h.h").write_text("#define T int\n", encoding="utf8")
    (inc_dir / "h.h").write_text("#define T 42\n", encoding="utf8")
    main = src_dir / "main.c"
    main.write_text('#include "h.h"\nT x;\n', encoding="utf8")
    r = run_pipeline_on_source(
        main.read_text(encoding="utf8"),
        rules_dir=PACK,
        quiet=True,
        include_dirs=[str(inc_dir)],
        input_path=str(main),
    )
    assert r["success"], r["error"]


def test_nested_include_two_levels(tmp_path):
    """嵌套：a.h → b.h，b 里的宏在宿主生效。"""
    (tmp_path / "b.h").write_text("#define T int\n", encoding="utf8")
    (tmp_path / "a.h").write_text('#include "b.h"\n', encoding="utf8")
    r = _run('#include "a.h"\nT x;\n', tmp_path)
    assert r["success"], r["error"]


def test_define_from_header_expands(tmp_path):
    """被包含文件的 `#define` 在宿主代码里生效（分析面证据 = 解析通过）。"""
    (tmp_path / "defs.h").write_text("#define VALUE 42\n", encoding="utf8")
    r = _run('#include "defs.h"\nint x = VALUE;\n', tmp_path)
    assert r["success"], r["error"]
    # 渲染面仍保留宏引用（不展开成 42）——与宏还原语义一致
    assert "VALUE" in r["output"]


def test_missing_include_is_controlled_diagnostic(tmp_path):
    """缺文件 ⇒ 受控诊断（不抛异常；`error` 非空 + 结构化 `preprocessor_errors`）。"""
    r = _run("#include <nope_xyz.h>\nint x;\n", tmp_path)
    assert not r["success"]
    assert "include 文件未找到" in r["error"]
    diags = r["preprocessor_errors"]
    assert diags and diags[0]["kind"] == "missing"


def test_cycle_include_is_controlled_diagnostic(tmp_path):
    """循环包含 ⇒ `cycle` 诊断（不递归爆栈）。"""
    (tmp_path / "a.h").write_text('#include "b.h"\n', encoding="utf8")
    (tmp_path / "b.h").write_text('#include "a.h"\n', encoding="utf8")
    r = _run('#include "a.h"\nint x;\n', tmp_path)
    assert not r["success"]
    kinds = [d["kind"] for d in r["preprocessor_errors"]]
    assert "cycle" in kinds, kinds


def test_depth_limit_is_controlled_diagnostic(tmp_path):
    """深度超限（C 包 `max_depth=32`）⇒ `depth` 诊断。"""
    for i in range(40):
        (tmp_path / f"d{i}.h").write_text(
            f'#include "d{i + 1}.h"\n', encoding="utf8"
        )
    r = _run('#include "d0.h"\nint x;\n', tmp_path)
    assert not r["success"]
    kinds = [d["kind"] for d in r["preprocessor_errors"]]
    assert "depth" in kinds, kinds


def test_render_keeps_include_line_and_is_idempotent(tmp_path):
    """渲染：`#include` 原行保留、内容不内联、两遍幂等。"""
    (tmp_path / "h.h").write_text("int hdr_var;\n", encoding="utf8")
    src = '#include "h.h"\nint x;\n'
    r1 = _run(src, tmp_path)
    assert r1["success"], r1["error"]
    out1 = r1["output"]
    assert "#include" in out1 and "hdr_var" not in out1
    r2 = _run(out1, tmp_path)
    assert r2["success"], r2["error"]
    assert r2["output"] == out1, "include 文件两遍渲染必须幂等"


def test_include_inside_function_body_falls_back_to_verbatim(tmp_path):
    """退化路径：`#include` 在函数体内（内容落语句中间）⇒ 整文件原文输出。

    不硬剪（会切在语句中间）；退化为原文输出 ⇒ 幂等、绝不内联。
    """
    (tmp_path / "stmts.h").write_text("int y;\n", encoding="utf8")
    src = 'void f(void) {\n#include "stmts.h"\n}\n'
    r = _run(src, tmp_path)
    assert r["success"], r["error"]
    assert "hdr_var" not in r["output"]
    assert r["output"].strip() == src.strip() or "int y;" not in r["output"]
