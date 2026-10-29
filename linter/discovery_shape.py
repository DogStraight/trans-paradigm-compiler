"""discovery_shape.py — 语句发现的形态声明（语言包 `[discovery]`）。

**为什么声明而不是推导**（ADR-0025）：linter 要在**没有 parser** 的前提下切语句边界
（坏输入也要能逐句定位），因此需要知道"语法形状"：哪些规则是括号定界的语句容器、
属性前缀对是什么、哪些关键字是容器延续、哪些 token 是子句分隔符。

这些是**语言事实**，不能靠引擎从 production 结构猜：
`[[nodiscard]] int f(void){...}` 与 `{...}` 在结构上同形（都是"定界 token + 语句引用"），
区分依据是**语义意图**。实测旧推导 `_is_bracket_stmt_container` 对 `PortParens` /
`Range` / `InitList` / `StructBody` 等大量非容器规则同样返回 True——证明它在猜。

声明形态（`grammar/<lang>/base/_discovery.toml`）：

    [discovery]
    containers        = ["CompoundStmt"]            # 括号定界语句容器（body 递归发现）
    continuations     = ["keyword.else"]            # 容器延续关键字
    prefix_pairs      = [["bracket.l_parentheses", "symbol.base.multiple"]]  # 属性对
    clause_separators = ["symbol.base.colon"]       # 子句分隔符

未声明本段 = 该语言没有这些形态（引擎按空集处理，**不猜**、不静默降级为推导）。

Doc: docs/decisions/0025-discovery-rule-derivation.md
Doc: linter/linter_architecture.md（发现层）
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config_registry import declare_cfg
from core.errors import ConfigError
from core.token_protocol import split_token_types

# discovery.shape: 语句发现形态（语言包 tpc.toml `[discovery] shape = {file, section}`）
_shape_cfg: dict = declare_cfg("discovery.shape", {}, __name__, "_shape_cfg")


@dataclass(frozen=True)
class DiscoveryShape:
    """语句发现所需的语言形态（全部来自声明，引擎零语言知识）。"""

    containers: frozenset[str] = frozenset()
    continuations: frozenset[str] = frozenset()
    prefix_pairs: frozenset[tuple[str, str]] = frozenset()
    clause_separators: frozenset[str] = frozenset()

    def is_prefix_pair(self, opener: str, second: str) -> bool:
        """`(opener, second)` 是否声明的属性/修饰前缀对（整体跳过，不建语句节点）。"""
        return (opener, second) in self.prefix_pairs


def _parse_prefix_pairs(raw: object) -> frozenset[tuple[str, str]]:
    """`prefix_pairs` 声明 → 二元组集合。**畸形即 fail-fast**（ADR-0003）。

    不做"跳过不合法项"的静默降级：少一对前缀对会让属性区间的边界判定**悄悄**
    退回错误形态（属性内的括号/换行截断语句），而这种错误没有可见症状。
    """
    if raw is None:
        return frozenset()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(
            f"[discovery] prefix_pairs 应为列表的列表（[[开 token, 次 token], ...]），"
            f"实际是 {type(raw).__name__}"
        )
    pairs: set[tuple[str, str]] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ConfigError(
                f"[discovery] prefix_pairs[{i}] 应为 [开 token, 次 token] 二元组，"
                f"实际是 {item!r}"
            )
        first, second = item
        if not isinstance(first, str) or not isinstance(second, str):
            raise ConfigError(
                f"[discovery] prefix_pairs[{i}] 两个元素都必须是字符串（token 名），"
                f"实际是 {item!r}"
            )
        pairs.add((first, second))
    return frozenset(pairs)


def load_shape() -> DiscoveryShape:
    """从已加载的语言包配置构造形态（`ConfigRegistry.load_all` 之后调用）。"""
    raw = _shape_cfg or {}
    pairs = _parse_prefix_pairs(raw.get("prefix_pairs"))
    return DiscoveryShape(
        containers=frozenset(raw.get("containers") or ()),
        continuations=frozenset(raw.get("continuations") or ()),
        prefix_pairs=pairs,
        clause_separators=frozenset(raw.get("clause_separators") or ()),
    )


def is_stmt_container(
    shape: DiscoveryShape, tree: dict, rule: object, opener: str | None = None
) -> bool:
    """`rule` 是否为**声明的**括号定界语句容器（`opener` 给定时还须是它的首 token）。

    单一判定口径，供两处共用（ADR-0025 D3）：
      - 发现层（`discovery._discover_bracket`）：决定"整体跳过括号区间"还是"转块分支递归 body"；
      - 注册层（`scanner._register_discovery_checkers`）：父检查器是否让位给子节点检查器。
    旧实现是两处各写一份近乎逐行的结构启发式（且对非容器规则大量误判）。
    """
    if not isinstance(rule, str) or rule not in shape.containers:
        return False
    if opener is None:
        return True
    info = tree.get(rule) or {}
    prods = info.get("prods") or []
    if not prods:
        return False
    first = prods[0]
    if not isinstance(first, dict) or first.get("type") != "token":
        return False
    return opener in split_token_types(first.get("token_type", ""))
