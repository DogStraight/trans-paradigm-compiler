"""函数宏**调用点事实**的记录（`expand_tokens(out_invocations=...)`）。

背景（A2 ① 宏语义检查族）：实参个数校验需要"宏表 + 调用点上下文"，而宏调用在
展开期就被替换掉、AST 里不可见。故引擎在展开时记录**通用事实**（谁在哪儿被调用、
给了几槽实参、该调用点的宏表形参表），语义判定归语言包 check 族
（`grammar/c/plugins/checks/macro_args/`）。

生产同路：`scan_directives` → `expand_tokens`（同 `pipeline._stage_expand` /
`analyzer.structure.FilePipeline._expand_source`）。行/列是**输入文本（clean 源）
坐标**——回源到原始文件由调用方用 `clean_to_raw`/`clean_line_map` 做（见
`test_c_macro_args_checks.py` 的位置用例）。

Doc: preprocessor/README.md（宏调用点事实） / core/_protocol.py
"""
import pytest

from preprocessor import scan_directives
from preprocessor._expand import expand_tokens

pytestmark = pytest.mark.smoke

PACK = "grammar/c"


def _expand(src: str, record: bool = True):
    """生产同路展开；record=True 时收集调用点事实 → (输出, 事实列表)。"""
    macro_defs, func_macros, _b, _ph, _dl, clean, _map = scan_directives(src, PACK)
    invocations: list[dict] = []
    out, *_tail = expand_tokens(
        clean,
        macro_defs,
        rules_dir=PACK,
        func_macros=func_macros,
        out_invocations=invocations if record else None,
    )
    return out, invocations


def _slots(src: str) -> list[tuple]:
    """事实列表 → 便于断言的 `(name, slots, single_empty, params)` 元组。"""
    _, inv = _expand(src)
    return [
        (i["name"], i["slots"], i["single_empty"], tuple(i["params"]))
        for i in inv
    ]


# ── 槽数与单槽空判 ──────────────────────────────────────────


def test_two_arg_call_records_slots_and_params() -> None:
    assert _slots("#define F(a,b) a+b\nint x = F(1, 2);\n") == [
        ("F", 2, False, ("a", "b"))
    ]


def test_too_few_and_too_many_are_both_recorded() -> None:
    """事实层不判对错：少给/多给都记（判定归 check 族）。"""
    assert _slots("#define F(a,b) a+b\nint x = F(1);\n") == [
        ("F", 1, False, ("a", "b"))
    ]
    assert _slots("#define F(a,b) a+b\nint x = F(1, 2, 3);\n") == [
        ("F", 3, False, ("a", "b"))
    ]


def test_empty_parens_is_one_empty_slot() -> None:
    """`F()` = 1 个空实参槽（`slots == 1`）——对 1 形参宏合法、对 0 形参宏是 0 个实参。"""
    assert _slots("#define O(a) a\nint x = O();\n") == [("O", 1, True, ("a",))]
    assert _slots("#define Z() 1\nint x = Z();\n") == [("Z", 1, True, ())]
    assert _slots("#define Z() 1\nint x = Z( );\n") == [("Z", 1, True, ())]


def test_comment_only_argument_counts_as_empty() -> None:
    """注释在翻译阶段已换成空白、不是预处理 token ⇒ `Z(/*c*/)` 与 `Z()` 同。"""
    assert _slots("#define Z() 1\nint x = Z(/* c */);\n") == [
        ("Z", 1, True, ())
    ]


def test_non_empty_single_argument_is_not_blank() -> None:
    assert _slots("#define Z() 1\nint x = Z(2);\n") == [("Z", 1, False, ())]


def test_empty_arguments_between_separators() -> None:
    """`F(,)` = 2 个空实参槽（两槽都空，但槽数不是 1 ⇒ single_empty=False）。"""
    assert _slots("#define F(a,b) a+b\nint x = F(,);\n") == [
        ("F", 2, False, ("a", "b"))
    ]


def test_variadic_params_are_kept_verbatim() -> None:
    """形参表原样记录（变参占位由语言包声明，引擎不解释）。"""
    assert _slots("#define V(a, ...) a\nint x = V(1, 2);\n") == [
        ("V", 2, False, ("a", "..."))
    ]
    assert _slots("#define V(...) __VA_ARGS__\nint x = V();\n") == [
        ("V", 1, True, ("...",))
    ]


# ── 位置（输入文本 clean 坐标）────────────────────────────────


def test_position_is_name_column_and_line() -> None:
    out, inv = _expand("#define F(a,b) a+b\nint x = F(1, 2);\n")
    assert inv[0]["line"] == 2
    assert inv[0]["column"] == 8  # `int x = F` 的 F 起列（0-based）
    assert out.splitlines()[1] == "int x = 1+2;"


def test_line_numbers_are_input_text_lines() -> None:
    """指令行被替换为 marker（1:1 保行）⇒ 行号直接是输入文本行号。"""
    _, inv = _expand("#define F(a) a\n\n\nint x = F(1);\n")
    assert inv[0]["line"] == 4


# ── 只记"真调用" ───────────────────────────────────────────


def test_nothing_recorded_without_out_list() -> None:
    """不传 out_invocations ⇒ 零开销、无副作用（既有调用点行为不变）。"""
    src = "#define F(a,b) a+b\nint x = F(1);\n"
    out_a, _ = _expand(src, record=False)
    out_b, inv = _expand(src, record=True)
    assert inv
    assert out_a == out_b  # 记录不改变展开结果


def test_object_like_macro_is_not_recorded() -> None:
    assert _slots("#define N 4\nint x = N;\n") == []


def test_function_macro_name_without_parens_is_not_recorded() -> None:
    """函数宏名裸出现不是调用（标准：不替换）⇒ 无事实。"""
    assert _slots("#define F(x) x+1\nint r = F;\n") == []


def test_undef_then_call_is_not_recorded() -> None:
    assert _slots(
        "#define F(a,b) a+b\n#undef F\nint x = F(1);\n"
    ) == []


def test_call_before_define_uses_final_macro_table() -> None:
    """守卫既有近似：现役展开器对**全文件用最终宏表**（非调用点宏表）⇒ 定义前的
    同名调用也会被替换、也会记录事实。

    这是**既有**近似（A1 之前就存在；与 GCC 的顺序语义不同），不是本机制引入；
    事实面随展开器口径走（检查与展开一致，不另造第二套语义）。真做顺序语义须
    展开器改按行推进宏表（另立项）。
    """
    assert _slots("int x = F(1);\n#define F(a,b) a+b\n") == [
        ("F", 1, False, ("a", "b"))
    ]


def test_redefinition_uses_final_params() -> None:
    """守卫既有近似：重定义前后形参不同时，各调用点记录的都是**最终**形参表。

    与上一条同根：展开器不做调用点宏表快照。影响面 = 重定义前后都有的同名调用
    会被按最终形参表判（check 侧口径与展开一致）；真实语料中该形态需显式
    `#undef` + 重定义，罕见。
    """
    src = (
        "#define F(a) a\nint x = F(1);\n"
        "#undef F\n#define F(a,b) a+b\nint y = F(1, 2);\n"
    )
    assert _slots(src) == [
        ("F", 1, False, ("a", "b")),
        ("F", 2, False, ("a", "b")),
    ]


def test_call_in_inactive_condition_is_not_recorded() -> None:
    """`#if 0` 分支在扫描期被压缩掉 ⇒ 不展开、无事实（与 gcc 同上）。"""
    src = "#if 0\n#define F(a,b) a+b\nF(1);\n#endif\n"
    assert _slots(src) == []


def test_multiline_call_is_not_recorded() -> None:
    """已声明边界（A1 ②）：实参跨行的调用不展开 ⇒ 无事实。

    守卫式断言当前行为；边界落地（跨行实参）时必须显式改这里。
    """
    assert _slots("#define F(a,b) a+b\nint x = F(1,\n            2);\n") == []
