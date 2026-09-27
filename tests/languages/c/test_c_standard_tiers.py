"""tests/languages/c/test_c_standard_tiers.py — 标准档位对照（同进程内切三档）。

验证 ROADMAP 的"标准等效"主张：**同一份语法资产**（核心基线 + 插件目录），只改启用
清单 `[plugins] enabled`，就得到不同标准的语法接受域：

    档位            enabled                   `_Static_assert`（C11）      `static_assert`（C23）
    核心基线档      []                        ExprStmt（当调用表达式）     ExprStmt
    c11 档          ["c11"]                   StaticAssertDecl             ExprStmt
    真实包（c23）   ["c11","c17","c23"]       StaticAssertDecl             StaticAssertC23Decl

⚠ **未声明关键字 ≠ 拒绝**：关键字没声明时，`_Static_assert(1, "x");` 会被当作
**普通函数调用**（`ExprStmt`）**静默接受**——C 语法本就宽进（调用未声明的函数合法）。
"响亮失败"只在**关键字已声明但无规则**时出现（如 c23 插件里 `nullptr` 那类）。
故档位判据看的是**解析成哪个节点**，而不是"有没有报错"。

⚠ **做法说明**：用临时 pack 副本（`shutil.copytree`）改 `enabled` 一行——零引擎改动。
引擎侧若有 `enabled` 覆盖参数会更省事（已记 TODO），但**能力本身已具备**，本文件即证据。
"""

import os
import pathlib
import re
import shutil
import tomllib

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, iter_nodes
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_PACK = os.path.join(ROOT, "grammar", "c")

_C11_SRC = '_Static_assert(1, "x");\n'
_C23_SRC = 'static_assert(1, "x");\n'
# 块作用域形态（C11 §6.7.4 两处都合法）：档位判据要看"块内那支进没进 Stmt 交替"
_C11_BLOCK_SRC = 'void f(void) {\n    _Static_assert(1, "x");\n}\n'


def _make_pack(tmp_path, enabled: list[str]) -> str:
    """复制真实包到 tmp，只改 [plugins] enabled 一行。"""
    dst = tmp_path / "lang"
    shutil.copytree(_PACK, dst, dirs_exist_ok=True)
    tpc = dst / "tpc.toml"
    text = tpc.read_text(encoding="utf-8")
    text = re.sub(
        r"enabled = \[[^\]]*\]",
        "enabled = [" + ", ".join(f'"{n}"' for n in enabled) + "]",
        text,
    )
    tpc.write_text(text, encoding="utf-8")
    return str(dst)


def _parse_with(pack: str, src: str) -> list[str]:
    ConfigRegistry.load_language(pack, plugins_dir=os.path.join(pack, "plugins"))
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
    return [n.node_name for n in (getattr(ast, "sub_node", []) or [])]


def _all_with(pack: str, src: str) -> list[str]:
    """递归节点名（块内形态要看得到 FuncDef 里面的语句）。"""
    ConfigRegistry.load_language(pack, plugins_dir=os.path.join(pack, "plugins"))
    rules = setup_grammar(pack, GrammarRulesRegister())
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
    return [n.node_name for n in iter_nodes(ast)] if ast is not None else []


@pytest.fixture(autouse=True)
def restore_language():
    yield
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


class TestStandardTiers:
    def test_baseline_tier_has_no_plugin_nodes(self, tmp_path):
        """核心基线档（enabled 为空）：两种静态断言都不是插件节点。

        ⚠ 它们**不是被拒**，而是当普通调用表达式（`ExprStmt`）静默接受——
        判据是"解析成哪个节点"，不是"有没有报错"（见文件头注）。
        """
        pack = _make_pack(tmp_path, [])
        assert _parse_with(pack, _C11_SRC) == ["ExprStmt"]
        assert _parse_with(pack, _C23_SRC) == ["ExprStmt"]

    def test_c11_tier_accepts_only_c11_form(self, tmp_path):
        """c11 档：`_Static_assert` 走插件规则；小写 `static_assert` 仍是普通调用。"""
        pack = _make_pack(tmp_path, ["c11"])
        assert _parse_with(pack, _C11_SRC) == ["StaticAssertDecl"]
        assert _parse_with(pack, _C23_SRC) == ["ExprStmt"]

    def test_c23_tier_accepts_both(self, tmp_path):
        """c11+c17+c23 档：两种形态都可用（C23 保留 `_Static_assert` 向后兼容）。"""
        pack = _make_pack(tmp_path, ["c11", "c17", "c23"])
        assert _parse_with(pack, _C11_SRC) == ["StaticAssertDecl"]
        assert _parse_with(pack, _C23_SRC) == ["StaticAssertC23Decl"]

    def test_block_scope_follows_the_tier(self, tmp_path):
        """**块作用域**同样随档位变：基线档当普通调用（`ExprStmt`），c11 档进插件节点。

        这是"增量脚本真的接上了核心 `Stmt` 交替"的档位级判据——只看文件作用域会漏掉
        （文件作用域靠 `is_statement` + 全局语句发现，与注入无关）。
        ⚠ 基线档**不是拒绝**（未声明关键字 → `_Static_assert` 只是标识符，`(1,"x")`
        是调用）——判据仍是"解析成哪个节点"（见文件头注）。
        """
        base = _make_pack(tmp_path / "base", [])
        base_nodes = _all_with(base, _C11_BLOCK_SRC)
        assert "FuncDef" in base_nodes
        assert "StaticAssertDecl" not in base_nodes, base_nodes
        assert "ExprStmt" in base_nodes, base_nodes

        c11 = _make_pack(tmp_path / "c11", ["c11"])
        c11_nodes = _all_with(c11, _C11_BLOCK_SRC)
        assert "StaticAssertDecl" in c11_nodes, c11_nodes

    def test_only_enabled_line_differs(self, tmp_path):
        """三档之间**只差 `enabled` 一行**——"标准 = 启用清单组合"的可机械检查证据。"""
        a = _make_pack(tmp_path / "a", [])
        b = _make_pack(tmp_path / "b", ["c11", "c17", "c23"])
        ta = (pathlib.Path(a) / "tpc.toml").read_text(encoding="utf-8")
        tb = (pathlib.Path(b) / "tpc.toml").read_text(encoding="utf-8")
        diff = [
            (x, y)
            for x, y in zip(ta.splitlines(), tb.splitlines())
            if x != y
        ]
        assert len(diff) == 1, f"两档之间不止 enabled 一行不同：{diff}"
        assert "enabled" in diff[0][0]

    def test_plugin_dirs_identical_across_tiers(self, tmp_path):
        """两档的**插件目录内容完全相同**（同一份资产，差别只在启用清单）。"""
        a = pathlib.Path(_make_pack(tmp_path / "a", []))
        b = pathlib.Path(_make_pack(tmp_path / "b", ["c11", "c17", "c23"]))
        names_a = sorted(p.relative_to(a).as_posix() for p in (a / "plugins").rglob("*.toml"))
        names_b = sorted(p.relative_to(b).as_posix() for p in (b / "plugins").rglob("*.toml"))
        assert names_a == names_b and names_a, "插件目录应一致且非空"

    def test_real_pack_meta_matches_c23_tier(self):
        """真实包的启用清单等于最强档（c11+c17+c23）——避免"文档说一套、包里另一套"。"""
        with open(os.path.join(_PACK, "tpc.toml"), "rb") as f:
            enabled = tomllib.load(f)["plugins"]["enabled"]
        assert {"c11", "c17", "c23"} <= set(enabled)
