"""shared_components.py — 检查侧共享组件装载（按 `rules_dir` 缓存）。

`tpc check` 是独立于 pipeline 的执行入口，需要自己的一份组件：语法规则表 /
规则选择器 / lexer / linter / renderer。装载过程 = 配置加载
（`ConfigRegistry.load_all`）+ 插件组件发现（`load_all_components`）+
`setup_grammar` + 组件装配。

**为什么单独一个模块**（而不是留在 `analyzer/checker.py`）：门面
（`ProjectChecker`）的职责是**阶段编排 + 诊断汇总**，组件装载是另一件事——它
依赖配置/插件/词法/渲染四个子系统，且与 pipeline 侧的 `_PIPELINE_SHARED`
**刻意分离**（check 与 pipeline 各自缓存，不共享状态；见 checker 原注释）。

**缓存键 = `rules_dir`**：跨语言测试传入的独立 `GrammarRulesRegister` 都伴随
不同的 `rules_dir`（c4 vs verilog），故键足够。若将来出现"同 rules_dir、
不同 register"的用法，键需扩为 `(rules_dir, id(register))`。

Doc: analyzer/README.md（check 入口）
"""

from __future__ import annotations

import os


class SharedComponents:
    """按 `rules_dir` 缓存的共享组件：首次调用装载，后续复用同一份。"""

    _CACHE: dict[str, dict] = {}

    @staticmethod
    def _component_signature() -> tuple[tuple[str, str], ...]:
        """当前全局组件注册表的语言身份：(组件名, 组件目录)。

        组件名集合可能跨语言重名（都是开放声明集），单看名字会把"另一个语言"
        误认成本语言；目录参与签名后，语言身份是注册表内容关系而非名单。
        """
        from core.plugin_loader import _loaded_components

        return tuple(
            sorted(
                (
                    name,
                    str((info.get("meta") or {}).get("_dir", "")),
                )
                for name, info in _loaded_components.items()
            )
        )

    @classmethod
    def _activate(cls, rules_dir: str, ext_dirs: list[str]) -> None:
        """把全局组件注册表重建为 `rules_dir` 对应语言（缓存命中路径用）。"""
        from core.config_registry import ConfigRegistry
        from core.plugin_loader import load_all_components

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_dir = (
            rules_dir if os.path.isabs(rules_dir) else os.path.join(root, rules_dir)
        )
        plugins_dir = os.path.join(full_dir, "plugins")
        declared_optional, active_tier = ConfigRegistry.tier_state(full_dir)
        ConfigRegistry.load_all(full_dir, ext_dirs=ext_dirs, plugins_dir=plugins_dir)
        load_all_components(
            plugins_dir=plugins_dir,
            declared_optional=declared_optional,
            active_tier=active_tier,
        )

    @classmethod
    def get(cls, rules_dir: str, ext_dirs: list[str], register=None) -> dict:
        """取（必要时装载）该 `rules_dir` 的共享组件。

        Args:
            rules_dir: 语言包目录（相对路径按仓库根解析）；同时是缓存键。
            ext_dirs: 额外配置目录（透传 ConfigRegistry / setup_grammar）。
            register: 规则注册表；None = 全局默认单例（测试传独立实例以避免
                污染全局，见 tests/languages/c4/）。
        """
        cached = cls._CACHE.get(rules_dir)
        if cached is not None:
            # 跨语言同进程：别的语言 `setup_grammar` 会清空 `_loaded_components`；
            # 缓存命中只复用规则/词法对象还不够——组件注册表（postpass/原语/
            # capability）必须**重新建立为本语言**，否则第二次 C 检查的
            # CSC/LAB/MAC 全部静默丢失（C→verilog→C 实测）。
            if cls._component_signature() != cached.get("component_signature", ()):
                cls._activate(rules_dir, ext_dirs)
            return cached

        from core.config_registry import ConfigRegistry
        from core.define import GrammarRulesRegister
        from core.plugin_loader import load_all_components
        from lexer import Lexer
        from linter.scanner import LinterScanner
        from parser import setup_grammar
        from parser.rule_selector import RuleSelector
        from renderer import Renderer

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_dir = (
            rules_dir if os.path.isabs(rules_dir) else os.path.join(root, rules_dir)
        )
        plugins_dir = os.path.join(full_dir, "plugins")
        # 配置加载 + 插件组件发现（postpass/原语注册依赖此步骤；
        # 与 pipeline 一致——pipeline 在模块导入时顶层调用）
        ConfigRegistry.load_all(full_dir, ext_dirs=ext_dirs, plugins_dir=plugins_dir)
        load_all_components()

        reg = register or GrammarRulesRegister.get_default()
        rules = setup_grammar(full_dir, reg, ext_dirs=ext_dirs)
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        # 词法组件先落到局部名：渲染器要取它的行终止型注释词表（见下）
        lexer = Lexer(rules_dir=full_dir, ext_dirs=ext_dirs)
        shared = {
            "rules": rules,
            "rule_selector": RuleSelector(rules, stmt_names),
            "lexer": lexer,
            # 独立 register 必须透传：LinterScanner 内部 setup_grammar 默认用
            # 全局单例 get_default()，跨语言（c4）检查会把 c4 规则灌进单例且
            # 无法靠 ConfigRegistry 恢复（test_c4_linter 同款坑）。
            "linter": LinterScanner(
                rules_dir=full_dir, ext_dirs=ext_dirs, register=reg
            ),
            # ⚠ 行终止型注释词表必须与主管线（pipeline/__init__.py 的 Renderer 构造）同口径：
            #   缺它时引擎不认识任何注释标点，渲染**子树**（参数默认值/覆盖、宽度、
            #   连接信号）时行注释会把同行后续元素吃进注释文本 ⇒ 产物文本静默丢 token
            #   （实测 `param_default` 的 `4 // note + 2` vs 接线后的 `4 + 2 // note`）。
            "renderer": Renderer(
                rules_dir=full_dir,
                line_comment_starts=lexer.line_terminating_comment_starts(),
            ),
            "component_signature": (),
        }
        shared["component_signature"] = cls._component_signature()
        cls._CACHE[rules_dir] = shared
        return shared
