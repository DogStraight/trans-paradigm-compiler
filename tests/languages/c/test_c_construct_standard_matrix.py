"""tests/languages/c/test_c_construct_standard_matrix.py — 判据 4：构造 × 标准档位断言面。

退出判据 4 = "各标准档位断言面：每条构造断'属哪个标准 + 接受/拒绝各一条'"。本文件把
`tools/c_acceptance.py::CASES`（**49 条接受面清单**，与缺口档「接受域现状」逐行对照）逐条
挂上**标准归属**，并断言：

1. **归属**：每条构造属于 C99 / C11 / C23（C17 是缺陷修正版，**无新语法**——见
   `grammar/c/plugins/c17/tpc.toml` 头注，本矩阵不出现 C17 归属）；
2. **接受**：在该标准档位解析**完整**（`_parse_truncated is False`）且出现该构造的
   标准增量节点（C99 构造在 baseline 档即可）；
3. **拒绝（下档不可见）**：C11/C23 构造在**下档**必须不可见——下档解析要么截断、
   要么不含该构造的增量节点（**口径注**：C 语法宽进，未声明关键字常被当普通调用
   `ExprStmt` 静默接受，故"拒绝"看的是**节点形态**而非报错；与 `test_c_standard_tiers.py`
   头注同口径）。

预处理两条（`#include` / `#define`）不在此矩阵（它们走预处理器而非解析器）：接受面由
`tests/e2e/test_c_include_e2e.py` 等 A2 判据覆盖，本文件只断言其**归属 C99**（清单对齐）。

⚠ 清单是**声明式维护**：新增 `CASES` 行必须同步本文件的 `_OWNERSHIP`（meta 测试守）。
Doc: `docs/gaps/gap-language-pack-scope.md`（接受域现状）、`PROGRESS.md`（退出判据 4）
"""

import os

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector

from tests.languages.c.test_c_standard_tiers import _PACK, _TIERS
from tools.c_acceptance import CASES

#: 每条 c_acceptance 构造的标准归属。C17 不出现（无新语法）。
_OWNERSHIP: dict[str, str] = {
    # ── C99（基线档全部接受；无下档，拒绝面由 conformance/lint 语料承担）──
    "整数后缀 U/L/LL": "C99",
    "十六进制 + 后缀": "C99",
    "八进制": "C99",
    "科学计数浮点": "C99",
    "浮点后缀": "C99",
    "前导点浮点 `.5`": "C99",
    "字符串内转义引号": "C99",
    "字符字面量与转义": "C99",
    "函数指针": "C99",
    "二级指针": "C99",
    "多词说明符 + 限定符": "C99",
    "函数说明符 inline": "C99",
    "变参 `...`": "C99",
    "类型词 _Bool/_Complex": "C99",
    "指示符初始化": "C99",
    "struct/union/enum": "C99",
    "位域": "C99",
    "控制流全族": "C99",
    "三目": "C99",
    "逗号运算符": "C99",
    "强制转换 (T)x": "C99",
    "sizeof(T)": "C99",
    "链式成员 a.b.c": "C99",
    "调用后下标 f(x)[i]": "C99",
    "复合字面量": "C99",
    "#include": "C99",
    "#define": "C99",
    "说明符顺序（存储类/限定符 + typedef 名）+ 指针限定符": "C99",
    "无名抽象指针形参（原型声明 void f(void *, size_t)）": "C99",
    # ── C11（7 条）──
    "_Static_assert 文件作用域（c11 插件）": "C11",
    "_Static_assert 块作用域（c11，注入 Stmt 交替）": "C11",
    "_Alignof（c11，表达式原子）": "C11",
    "_Generic（c11，表达式原子）": "C11",
    "_Noreturn / _Thread_local（c11，说明符位）": "C11",
    "_Alignas（c11，说明符位；常量表达式与类型名两形态）": "C11",
    "_Atomic（c11，限定符位 + `_Atomic(T)` 说明符形态）": "C11",
    # ── C23（13 条）──
    "nullptr / true / false（c23，表达式原子）": "C23",
    "bool / typeof / constexpr（c23，说明符位）": "C23",
    "c23 小写拼写（static_assert 块作用域 / alignas / alignof / thread_local）": "C23",
    "c23 单参静态断言下划线拼写（_Static_assert(1)，§6.7.10）": "C23",
    "c23 类型词（_BitInt(N) / _Decimal32·64·128）": "C23",
    "c23 属性说明符（[[nodiscard]] / 带前缀 / 多实参 / 尾随逗号 / 属性声明）": "C23",
    "c23 属性位点：声明符内（标识符之后，§6.7.6）": "C23",
    "c23 属性位点：枚举项（`=` 之前，§6.7.2.2）": "C23",
    "c23 十进制浮点字面量后缀（1.5df / 1.5dd / 1.5dl）": "C23",
    "字面量前缀族（L / u / U / u8，按档位声明）": "C23",
    "c23 二进制常量（0b1010 / 0B1010ULL）": "C23",
    "c23 数字分隔符（1'000'000 / 0x1'F / 0b1'0）": "C23",
    "c23 枚举固定底层类型（enum e : int，§6.7.2.2）": "C23",
}

#: 该构造在"其标准档"应出现的增量节点（任一出现即可）；空 = 纯词法形态（按下档截断判定）。
_MARKERS: dict[str, tuple[str, ...]] = {
    "_Static_assert 文件作用域（c11 插件）": ("StaticAssertDecl",),
    "_Static_assert 块作用域（c11，注入 Stmt 交替）": ("StaticAssertDecl",),
    "_Alignof（c11，表达式原子）": ("AlignofExpr",),
    "_Generic（c11，表达式原子）": ("GenericSelection",),
    "_Noreturn / _Thread_local（c11，说明符位）": ("NoreturnSpec", "ThreadLocalSpec"),
    "_Alignas（c11，说明符位；常量表达式与类型名两形态）": (
        "AlignasConstSpec",
        "AlignasTypeSpec",
    ),
    "_Atomic（c11，限定符位 + `_Atomic(T)` 说明符形态）": ("AtomicSpec",),
    "nullptr / true / false（c23，表达式原子）": ("NullptrLiteral", "BoolLiteral"),
    "bool / typeof / constexpr（c23，说明符位）": (
        "BoolType",
        "TypeofSpec",
        "ConstexprSpec",
    ),
    "c23 小写拼写（static_assert 块作用域 / alignas / alignof / thread_local）": (
        "StaticAssertC23MsgDecl",
        "AlignasC23Spec",
        "AlignofC23Expr",
        "ThreadLocalC23Spec",
    ),
    "c23 单参静态断言下划线拼写（_Static_assert(1)，§6.7.10）": (
        "StaticAssertC23UnderscoreNoMsgDecl",
    ),
    "c23 类型词（_BitInt(N) / _Decimal32·64·128）": ("BitIntSpec", "DecimalSpec"),
    "c23 属性说明符（[[nodiscard]] / 带前缀 / 多实参 / 尾随逗号 / 属性声明）": (
        "AttributeSpec",
    ),
    "c23 属性位点：声明符内（标识符之后，§6.7.6）": ("AttributeSpec",),
    "c23 属性位点：枚举项（`=` 之前，§6.7.2.2）": ("AttributeSpec",),
    "c23 十进制浮点字面量后缀（1.5df / 1.5dd / 1.5dl）": ("DecimalSpec",),
    # 纯词法形态（词法前缀/数字分隔符/二进制常量）：节点名不体现，下档靠"是否截断"判定
    "字面量前缀族（L / u / U / u8，按档位声明）": (),
    "c23 二进制常量（0b1010 / 0B1010ULL）": (),
    "c23 数字分隔符（1'000'000 / 0x1'F / 0b1'0）": (),
    "c23 枚举固定底层类型（enum e : int，§6.7.2.2）": ("EnumUnderlyingType",),
}

_TIER_BY_STANDARD = {"C99": "baseline", "C11": "c11", "C23": "c23"}
_BELOW_TIER_BY_STANDARD = {"C11": "baseline", "C23": "c11"}
_PREPROCESSING = {"#include", "#define"}


def _parse_at(pack: str, src: str, enabled: list[str] | None) -> tuple[list[str], bool]:
    """按档位加载并解析 → (递归节点名, 是否截断)。"""
    ConfigRegistry.load_language(
        pack, plugins_dir=os.path.join(pack, "plugins"), enabled=enabled
    )
    register = GrammarRulesRegister()
    rules = setup_grammar(pack, register)
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=pack, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=pack)
    ast = parser.parse(lexer.tokenize(src))
    nodes = [n.node_name for n in iter_nodes(ast)] if ast is not None else []
    return nodes, bool(getattr(parser, "_parse_truncated", False))


@pytest.fixture(autouse=True)
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


class TestConstructStandardMatrix:
    """逐构造：标准归属 + 标准档接受 + 下档不可见。"""

    def test_清单与归属表一一对应(self):
        labels = {label for _family, label, _src in CASES}
        assert labels == set(_OWNERSHIP), (
            f"清单与归属表不一致：缺归属 {sorted(labels - set(_OWNERSHIP))}；"
            f"多余归属 {sorted(set(_OWNERSHIP) - labels)}"
        )
        assert set(_OWNERSHIP.values()) <= {"C99", "C11", "C23"}, "C17 无新语法，不应出现"
        markers = set(_MARKERS) | _PREPROCESSING
        assert markers <= set(_OWNERSHIP), sorted(markers - set(_OWNERSHIP))

    def test_c17_插件不带语法文件(self):
        """C17 是缺陷修正版：插件目录只有清单（无规则文件）——归属表不出现 C17 的事实依据。"""
        c17 = os.path.join(_PACK, "plugins", "c17")
        files = sorted(
            name for name in os.listdir(c17) if name.endswith(".toml")
        )
        assert files == ["tpc.toml"], files

    @pytest.mark.parametrize(
        "label,src,standard",
        [
            (label, src, _OWNERSHIP[label])
            for _family, label, src in CASES
            if label not in _PREPROCESSING
        ],
        ids=[
            label
            for _family, label, _src in CASES
            if label not in _PREPROCESSING
        ],
    )
    def test_标准档接受(self, label: str, src: str, standard: str) -> None:
        nodes, truncated = _parse_at(_PACK, src, _TIERS[_TIER_BY_STANDARD[standard]])
        assert not truncated, f"{label}: 在 {standard} 档解析被截断"
        assert nodes, f"{label}: 空 AST"
        markers = _MARKERS.get(label, ())
        if markers:
            assert any(m in nodes for m in markers), (
                f"{label}: {standard} 档缺增量节点 {markers}（实际 {sorted(set(nodes))[:12]}…）"
            )

    @pytest.mark.parametrize(
        "label,src,standard",
        [
            (label, src, _OWNERSHIP[label])
            for _family, label, src in CASES
            if label not in _PREPROCESSING and _OWNERSHIP[label] != "C99"
        ],
        ids=[
            label
            for _family, label, _src in CASES
            if label not in _PREPROCESSING and _OWNERSHIP[label] != "C99"
        ],
    )
    def test_下档不可见(self, label: str, src: str, standard: str) -> None:
        """下档口径：截断，或**不含**该构造的增量节点（宽进静默接受其他形态是允许的）。"""
        nodes, truncated = _parse_at(_PACK, src, _TIERS[_BELOW_TIER_BY_STANDARD[standard]])
        if truncated:
            return
        markers = _MARKERS.get(label, ())
        if not markers:
            # 纯词法形态且未截断 ⇒ 该形态在"下档"被完整接受（词法泄漏）——必须红
            pytest.fail(f"{label}: 下档未截断（词法增量泄漏到 {standard} 之前）")
        leaked = [m for m in markers if m in nodes]
        assert not leaked, f"{label}: 下档出现增量节点 {leaked}"

    def test_预处理构造归属_c99(self):
        for label in _PREPROCESSING:
            assert _OWNERSHIP[label] == "C99", label
