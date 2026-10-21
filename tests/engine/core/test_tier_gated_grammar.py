"""组件 grammar 文件按档位门控（ADR-0023）的引擎判据。

背景：`enabled` 长期只门控**声明面**，插件规则文件由 `setup_grammar` →
`load_all_components(<pack>/plugins)` **无条件**加载 ⇒ "档位 = 接受域"对**不依赖新
关键字的增量**不成立（C23 的 `[[属性]]` 是最初一例，随后两条标准缺口被它卡住）。
ADR-0023 的语义：**可选件**（包内 `[plugins] enabled` 清单里列出的组件名）的
`[grammar] files` 只在档位启用它时加载；**未列出的组件是常驻件**（C 的
`semantics` / `checks/*`），grammar 与 Python 都照旧——Python 组件永不按档位门控
（"怎么分析"不是"收哪些语法"）。

判据两条：① 可选件规则随档位出现/消失（规则表级，不经解析，能直接定位"漏加载"）；
② 常驻组件与 Python 面不受门控（`_loaded_components` 仍含语义/检查组件）。
非语言包目录（低层契约 / 临时目录）→ 两者皆空 ⇒ 不过滤（旧行为），由 `tier_state` 守。
"""

import os

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from core.plugin_loader import _loaded_components
from linter.scanner import LinterScanner
from parser import setup_grammar

_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")
_ALL = ["c11", "c17", "c23"]


def _rules_at(enabled: list[str]) -> dict:
    """按档位加载 C 包并返回规则表（与生产路径同入口）。"""
    ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=enabled)
    return setup_grammar(_PACK, GrammarRulesRegister())


class TestGrammarFollowsTier:
    def test_baseline_has_no_optional_component_rules(self):
        rules = _rules_at([])
        for name in ("AttributeSpec", "StaticAssertDecl", "StaticAssertC23MsgDecl"):
            assert name not in rules, f"基线档不该加载 {name}（可选件 grammar 未门控？）"

    def test_c11_adds_its_rules_only(self):
        rules = _rules_at(["c11"])
        assert "StaticAssertDecl" in rules, "c11 档缺 c11 规则"
        assert "AttributeSpec" not in rules, "c11 档不该有 c23 属性规则"

    def test_c23_adds_everything(self):
        rules = _rules_at(_ALL)
        for name in ("StaticAssertDecl", "StaticAssertC23MsgDecl", "AttributeSpec"):
            assert name in rules, f"c23 档缺 {name}"

    def test_rule_count_grows_with_tier(self):
        """规则数随档位单调增——比逐个规则名更能抓住"整体漏加载"。"""
        counts = [len(_rules_at(tier)) for tier in ([], ["c11"], _ALL)]
        assert counts[0] < counts[1] < counts[2], counts


class TestResidentComponentsUnaffected:
    def test_python_components_still_load_at_baseline(self):
        """常驻件（不在可选件清单里）**组件**照旧装载：只滤 grammar 文件。"""
        _rules_at([])
        for name in ("semantics", "macro_args", "labels"):
            assert name in _loaded_components, f"常驻组件 {name} 被档位门控误伤"

    def test_baseline_rules_still_have_core_constructs(self):
        rules = _rules_at([])
        for name in ("TranslationUnit", "StructBody", "AttributeSlot"):
            assert name in rules, f"核心规则 {name} 不该受门控影响"


class TestImplicitConsumersFollowTier:
    """**隐式消费方也跟随登记档位**（`load_language(enabled=…)` 之后无需再传参数）。

    缺陷态（循环 #41 实测）：`LinterScanner.__init__` 的 `load_all(enabled=None)` 会把该包
    档位重置成**包内清单**（c23 全档）⇒ 引擎级切档只对 parse 生效，linter 静默回到默认档：
    c11 档里 `_BitInt(8) a;`（C23 类型词，下档是标识符 ⇒ 整条声明解析失败）会被当合法代码
    零诊断放行。修法 = 构造时按 `tier_state` 把当前档位**显式**传给 `load_all`。
    """

    def test_linter_follows_recorded_tier_without_extra_param(self):
        src = "_BitInt(8) a;\n"
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=["c11"])
        assert LinterScanner(rules_dir=_PACK, register=GrammarRulesRegister()).scan(src), (
            "c11 档：linter 零诊断（档位泄漏成 c23，静默接受 C23 类型词）"
        )
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=_ALL)
        assert LinterScanner(rules_dir=_PACK, register=GrammarRulesRegister()).scan(src) == [], (
            "c23 档：合法标准代码被误诊（应为零诊断）"
        )


class TestTierStateLookup:
    """`tier_state` 的两类调用风格（相对 / 绝对包路径）都要命中同一档位。

    回归：登记键是 `load_language` 手里的路径原样，只按一种风格查会静默退回包内
    清单 ⇒ 门控失效且**无报错**（实测：测试用绝对 `_PACK`、生产用相对路径）。
    """

    def test_absolute_pack_lookup_sees_overridden_tier(self):
        abs_pack = os.path.abspath(_PACK)
        ConfigRegistry.load_language(abs_pack, plugins_dir=_PLUGINS, enabled=["c11"])
        declared, active = ConfigRegistry.tier_state(abs_pack)
        assert declared == ("c11", "c17", "c23")
        assert active == ("c11",), active

    def test_relative_pack_lookup_sees_overridden_tier(self):
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS, enabled=["c11"])
        declared, active = ConfigRegistry.tier_state(_PACK)
        assert declared == ("c11", "c17", "c23")
        assert active == ("c11",), active

    def test_tier_keys_cover_both_path_styles(self):
        """键候选集：相对调用补绝对键、绝对调用补相对键（跨盘符只留原样）。"""
        rel_keys = ConfigRegistry._tier_keys(_PACK)
        assert "grammar/c" in rel_keys
        assert os.path.abspath(_PACK) in [os.path.normpath(k) for k in rel_keys]
        abs_keys = ConfigRegistry._tier_keys(os.path.abspath(_PACK))
        assert "grammar/c" in abs_keys

    def test_no_override_falls_back_to_declared_list(self):
        ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS)
        declared, active = ConfigRegistry.tier_state(_PACK)
        assert declared == active == ("c11", "c17", "c23")

    def test_non_pack_dir_returns_empty_state(self, tmp_path):
        declared, active = ConfigRegistry.tier_state(str(tmp_path))
        assert declared == active == ()
