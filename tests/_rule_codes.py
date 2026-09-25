"""_rule_codes.py — 诊断码的**单一来源**提取（供多个门禁共用一份实现）。

散点治理（0.1.3 WS2）：诊断码事实曾散在 6 处手写清单（声明式规则表、插件 handler、
变异注入器、评测基准映射、真实语料基线、文档码表）。收敛做法是**先建一份可复用的
提取器**，再让各登记点接上校验——两处各自实现提取逻辑本身就是新的散点。

来源两路（都在语言包侧，引擎零语言知识）：

    声明式规则表   `grammar/<lang>/plugins/**/rules/*.toml` 的 `[[checks]] id`
    插件 handler   源码里 `context.report(..., code="XXX")` 的**字符串字面量**
                   （ast 精确取关键字实参；正则漏过单字母前缀码 W101/W201 等 8 个）

⚠ 只取字面量：动态拼接的码无法静态枚举，会在"引用了未定义的码"方向暴露，不静默漏掉。

Doc: docs/gaps/gap-feature-scatter.md（步 2 收敛目标）
"""
from __future__ import annotations

import ast
import glob
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_RULES_DIR = "grammar/verilog"


def declared_codes(rules_dir: str = DEFAULT_RULES_DIR) -> set[str]:
    """声明式规则表的 id 集合（加载语言包后读取）。"""
    from analyzer.checker import ProjectChecker
    from core import check_registry

    ProjectChecker(rules_dir=rules_dir)  # 触发规则表加载
    return {str(r["id"]) for r in check_registry.get_check_rules(rules_dir)}


def source_codes(rules_dir: str = DEFAULT_RULES_DIR) -> set[str]:
    """插件 handler 源码里 `code=` 关键字实参的字符串字面量集合（ast 提取）。"""
    pattern = os.path.join(_ROOT, rules_dir, "plugins", "**", "*.py")
    codes: set[str] = set()
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=path)
            except SyntaxError:  # 语法错误的插件文件由其他测试负责
                continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "code":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                ):
                    codes.add(kw.value.value)
    return codes


def all_codes(rules_dir: str = DEFAULT_RULES_DIR) -> set[str]:
    """已定义码全集 = 声明式规则表 ∪ 插件 handler 字面量。"""
    return declared_codes(rules_dir) | source_codes(rules_dir)


def code_like(token: str) -> bool:
    """形如诊断码的串（1–4 个字母前缀 + 2–4 位数字）。

    ⚠ 前缀长度**必须允许 1 个字母**：`W101` / `W201` / `W202` 等 8 个位宽族码就是
    单字母前缀——首版写 `[A-Z]{2,4}` 把这 8 个码从校验面里静默漏掉（与
    `test_rule_coverage.py` 头注记的正则漏码是同一个坑，故此处显式记一笔）。
    """
    import re

    return bool(re.fullmatch(r"[A-Z]{1,4}\d{2,4}", token))
