"""规则可达性门禁 —— 每条已定义的诊断码都必须有正样本。

动机：`NC008` 曾长期是"死规则"（`GenvarDecl` 符号从未注册 → 判定永不
触发），而现有评测只覆盖两侧——正样本能检出、负样本不误报——**不覆盖
"某规则根本没进正样本"**。这个盲区让"配置错误导致规则永不触发"长期不可见，
且越晚发现代价越大（规则已写进文档/对外承诺）。

做法（自动枚举，不依赖人工登记）：
    已定义码  = 声明式规则表（check_registry.get_check_rules）
                ∪ 插件 handler 源码里的 `code=` 关键字实参（ast 提取）
    已入样本码 = samples/check_accuracy/expected.json 的 focus
    断言      已定义 - 已入样本 - KNOWN_GAPS == ∅

为何用 ast 而非正则：首版正则 `[A-Z]{2,3}\\d{3}` 漏掉了单字母前缀码
（W101/W201 等 8 个），把"未找到定义"误报成样本问题——提取本身也要
经得起检验，故用语法树精确取关键字实参。

KNOWN_GAPS：已定义但尚无样本的显式登记，**带上限**（照 linter 侧
`MAX_KNOWN_MISS` 的防滥用思路：豁免数量本身必须受约束，否则门禁可以
靠豁免维持绿色）。补样本后须同步下调上限。
"""

import importlib
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from tests import _rule_codes as rule_codes  # noqa: E402 码提取的单一实现（两门禁共用）

_RULES_DIR = "grammar/verilog"
_EXPECTED = os.path.join(
    "tests", "e2e", "samples", "check_accuracy", "expected.json"
)

# 已定义但尚无样本的码（显式登记 + 理由）；上限防止豁免无限增长。
# 首批暴露的两个缺口（TP002 role+invert 悬空 / TP006 invert 自反）已同批
# 补齐样本 → 当前豁免为空、上限 0；新增豁免必须同时上调上限并说明理由。
KNOWN_GAPS: dict[str, str] = {}
MAX_KNOWN_GAPS = 0


def _declared_codes() -> set[str]:
    """声明式规则表的 id 集合（加载语言包后读取）。"""
    return rule_codes.declared_codes(_RULES_DIR)


def _source_codes() -> set[str]:
    """插件 handler 源码里 `code=` 关键字实参的字面量集合（ast 提取）。"""
    return rule_codes.source_codes(_RULES_DIR)


def _sampled_codes() -> set[str]:
    """评测样本声明的期望码集合（focus）。"""
    with open(_EXPECTED, encoding="utf-8") as f:
        return {str(c) for c in json.load(f)["focus"]}


@pytest.fixture(scope="module")
def codes() -> tuple[set[str], set[str], set[str]]:
    return _declared_codes(), _source_codes(), _sampled_codes()


def test_every_defined_rule_has_sample(codes) -> None:
    """每条已定义码要么有样本，要么在 KNOWN_GAPS 里显式登记。"""
    declared, source, sampled = codes
    defined = declared | source
    missing = sorted(defined - sampled - set(KNOWN_GAPS))
    assert not missing, (
        "以下规则已定义但没有任何评测样本（无法证明其可达；"
        "补样本，或登记到 KNOWN_GAPS 并说明理由）：\n  " + "\n  ".join(missing)
    )


def test_known_gaps_within_limit(codes) -> None:
    """豁免数量受上限约束——防靠豁免维持绿色（虚假绿）。"""
    declared, source, _ = codes
    gaps = (declared | source) & set(KNOWN_GAPS)
    assert len(gaps) <= MAX_KNOWN_GAPS, (
        f"豁免数 {len(gaps)} 超过上限 {MAX_KNOWN_GAPS}：豁免是临时状态，"
        "不是长期出口"
    )


def test_stale_known_gaps_reported(codes) -> None:
    """豁免项若已补上样本（或码已删）→ 提示清理，避免豁免表变成化石。"""
    _, _, sampled = codes
    stale = sorted(k for k in KNOWN_GAPS if k in sampled)
    assert not stale, (
        f"以下码已有样本，请从 KNOWN_GAPS 删除并下调 MAX_KNOWN_GAPS：{stale}"
    )


def test_sample_codes_are_defined(codes) -> None:
    """反向核验：样本期望码必须能在规则表或插件源码里找到定义。

    防"样本写了拼错的码"——那种样本只会永远 MISS 或永不命中，让门禁
    看着在跑其实没测到东西。
    """
    declared, source, sampled = codes
    unknown = sorted(sampled - (declared | source))
    assert not unknown, f"样本期望码找不到定义（拼错？遗漏枚举源？）：{unknown}"


def test_extraction_sanity(codes) -> None:
    """枚举源自身非空且量级合理（防提取逻辑失效导致门禁假绿）。"""
    declared, source, sampled = codes
    assert len(declared) >= 10, f"声明式规则仅 {len(declared)} 条，提取可能失效"
    assert len(source) >= 8, f"插件源码码仅 {len(source)} 个，提取可能失效"
    assert len(sampled) >= 20, f"样本期望码仅 {len(sampled)} 个，疑样本被清空"
