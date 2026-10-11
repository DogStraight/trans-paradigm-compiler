"""_raw_bridge.py — 把 C 包的「类型名查询」接入引擎 raw 校验（语言知识落点）。

分工（"语言知识不进代码"）：
· 引擎侧（`analyzer/raw_contract.py` + `analyzer/primitives/_raw_validate.py`）只管
  读契约字段、逐名调查询、**不过即报错**；
· **哪些 kind 算类型名 / 标签属别的命名空间**由本包声明（`_p4_query.py` 的常量），
  本文件把它注册成引擎可调的查询（`query = "auto"` ⇒ 取本包注册的唯一查询）。

⚠ 校验发生在**遍历期**（raw 节点被走到时），此刻 C 包的后置产物还没物化
（postpass 在遍历结束后跑）——故用 `_api.product_from(analyzer, context)`：产物缺失时
现场从 `analyzer.all_symbols` 重建，拿到的正是"**走到该位置为止已声明**"的符号
（声明序语义天然成立；`raw_order` 另由契约字段给出，见 `_p4_query` 的顺序门）。
Doc: grammar/c/README.md（符号收集产物）/ docs/gaps/gap-c-semantic-base.md（P4 安全网）
"""
from __future__ import annotations

from typing import Any

from core.define import Node
from analyzer.raw_contract import register_raw_name_query
from grammar.c.plugins.semantics import _api, _p4_query

#: 本包查询名（引擎内建配置用 `auto`；显式声明时可用此名）
QUERY_NAME = "c_type_name"


def query_type_name(analyzer: Any, context: Any, node: Node, site: dict) -> bool:
    """`site` 处的名字在 C 语义下是否类型名（P4 判定，见 `_p4_query.is_type_name`）。"""
    del node  # 协议签名参数：判定所需的 site 字段已由引擎读出，本查询不消费节点
    product = _api.product_from(analyzer, context)
    records = product.get("records") or []
    use = _p4_query.UseSite(
        name=str(site.get("name", "")),
        scope=str(site.get("scope", "")),
        order=site.get("order"),
        line=site.get("line"),
        column=site.get("column"),
    )
    return _p4_query.is_type_name(use, records)


register_raw_name_query(QUERY_NAME, query_type_name)
