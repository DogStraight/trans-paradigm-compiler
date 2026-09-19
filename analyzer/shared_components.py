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
        shared = {
            "rules": rules,
            "rule_selector": RuleSelector(rules, stmt_names),
            "lexer": Lexer(rules_dir=full_dir, ext_dirs=ext_dirs),
            # 独立 register 必须透传：LinterScanner 内部 setup_grammar 默认用
            # 全局单例 get_default()，跨语言（c4）检查会把 c4 规则灌进单例且
            # 无法靠 ConfigRegistry 恢复（test_c4_linter 同款坑）。
            "linter": LinterScanner(
                rules_dir=full_dir, ext_dirs=ext_dirs, register=reg
            ),
            "renderer": Renderer(rules_dir=full_dir),
        }
        cls._CACHE[rules_dir] = shared
        return shared
