"""model.py — 语法配置 → 岛模型（复用 linter 内部推导组件）。

不写任何语言字面量：规则表、块起止符、FIRST 集、前瞻消歧、发现树全部由
`linter` 的推导组件从语言包 TOML 得出。本模块只负责装配与暴露最小 API：

    model = IslandModel.from_pack("grammar/verilog")
    tokens = model.tokenize(source)
    nodes = model.discover(tokens)     # DiscoveredNode 树（岛候选）

Doc: islands/README.md
"""

from __future__ import annotations

import os

from linter.checker import DiscoveredNode
from linter.scanner import LinterScanner


def ext_dirs_for(rules_dir: str) -> list[str]:
    """语言包插件目录约定：`<pack>/plugins`（存在才算），与 linter/oracle 同源。"""
    plugins = os.path.join(rules_dir, "plugins")
    return [plugins] if os.path.isdir(plugins) else []


class IslandModel:
    """一个语言包的岛推导模型（构造一次，可跨文件复用）。"""

    def __init__(self, rules_dir: str, ext_dirs: list[str] | None = None) -> None:
        self.rules_dir = rules_dir
        self.ext_dirs = ext_dirs if ext_dirs is not None else ext_dirs_for(rules_dir)
        # LinterScanner 构造时完成配置加载 + setup_grammar + 切片树 + 块/括号起止符
        # + 前瞻表 + Discovery 装配；islands 直接消费其发现层与词法器。
        self._scanner = LinterScanner(self.rules_dir, ext_dirs=self.ext_dirs)
        self.lexer = self._scanner.lexer
        self._discovery = self._scanner._discovery

    def tokenize(self, source: str):
        """原始源文本 → token 流（不展开宏：含宏区间由 water 判定跳过）。"""
        return self.lexer.tokenize(source)

    def discover(self, tokens) -> list[DiscoveredNode]:
        """token 流 → 岛候选树（DiscoveredNode：rule/start/end/children）。"""
        return self._discovery.discover(tokens)

    def unrecognized(self):
        """本次 discover 的未识别位点（water 的另一来源）。"""
        return self._discovery.unrecognized_sites()
