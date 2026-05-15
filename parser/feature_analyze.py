from typing import Optional, Tuple
import re


class ProductionNode:
    def __init__(self, type: str, value: str, child: list["ProductionNode"]) -> None:
        self.type = type
        self.value = value
        self.child = child


def analyze_production_features(production: str) -> Optional[ProductionNode]:
    """
    分析产生式特征（返回树形结构），作为独立函数（staticmethod）

    Args:
        production: 产生式字符串

    Returns:
        ProductionNode: 产生式特征树的根节点（None表示空产生式）
    """

    def find_outermost_paren(s: str) -> Tuple[int, int] | None:
        """找到最外层括号的起止索引（优先处理最外层）"""
        stack = []
        outermost = None
        for i, c in enumerate(s):
            if c == "(":
                stack.append(i)
            elif c == ")" and stack:
                start = stack.pop()
                if not stack:  # 栈空 = 最外层括号
                    outermost = (start, i)
        return outermost

    # 用于保存括号节点，避免重复构建
    node_dict = {}

    def build_tree(s: str) -> Optional[ProductionNode]:
        """递归构建产生式特征树"""
        s = s.strip().replace(" ", "")
        if not s:
            return None

        # 1. 优先处理最外层括号
        paren = find_outermost_paren(s)
        if paren:

            start, end = paren
            before = s[:start].strip()  # 括号前的内容
            inner = s[start + 1 : end].strip()  # 括号内的内容
            after = s[end + 1 :].strip()  # 括号后的内容
            inner_node = build_tree(inner)
            # 生成稳定的 8 位十六进制 id（去符号并取低 32 位，然后零填充为8位小写 hex）
            hex_id = f"{(abs(hash(inner)) & 0xFFFFFFFF):08x}"
            node_dict[f"paren_{hex_id}"] = (inner_node, inner)
            s = "".join([before, f"paren_{hex_id}", after])
            return build_tree(s)

        # 匹配形如 "paren_0123abcd" 的键（8 位十六进制）
        if re.match(r"^paren_[0-9a-f]{8}$", s):
            return node_dict[s][0]

        # 2. 处理序列（,）：分割后递归构建子节点
        if "," in s:
            parts = [p.strip() for p in s.split(",") if p.strip()]
            child_nodes = [node for part in parts if (node := build_tree(part))]
            return ProductionNode(type="sequence", value="", child=child_nodes)

        # 3. 处理分支（|）：分割后递归构建子节点
        if "|" in s:
            parts = [p.strip() for p in s.split("|") if p.strip()]
            child_nodes = [node for part in parts if (node := build_tree(part))]
            return ProductionNode(type="branch", value="", child=child_nodes)

        # 4. 处理重复（*）：作用于整个前置单元
        if s.endswith("*"):
            base = s[:-1].strip()
            base = base if base not in node_dict.keys() else node_dict[base][1]
            base_node = build_tree(base)
            return ProductionNode(
                type="repeat", value=base, child=[base_node] if base_node else []
            )

        # 5. 处理可选（?）：作用于整个前置单元
        if s.endswith("?"):
            base = s[:-1].strip()
            base = base if base not in node_dict.keys() else node_dict[base][1]
            base_node = build_tree(base)
            return ProductionNode(
                type="optional", value=base, child=[base_node] if base_node else []
            )

        # 6. 处理语法调用（@）：无子女，value存去掉@的名称
        if s.startswith("@") and len(s) > 1 and s[1:].isalnum():
            base = s[1:]
            return ProductionNode(type="grammar_call", value=base, child=[])

        # 7. 普通token：无子女，value存token名称
        if re.match(r"^[a-zA-Z_\.]+$", s):
            return ProductionNode(type="normal", value=s, child=[])

        # 无效格式抛出异常
        raise Exception(f"无效的产生式格式: {s}")

    try:
        return build_tree(production)
    except Exception as e:
        raise Exception(f"分析产生式失败 {production}: {str(e)}")
