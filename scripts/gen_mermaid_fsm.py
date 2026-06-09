"""
从 NumberFSM._TRANSITIONS 表自动生成 Mermaid stateDiagram-v2 源码。

用法：
    python scripts/gen_mermaid_fsm.py              # 输出到控制台
    python scripts/gen_mermaid_fsm.py -o fsm.md    # 写入文件
"""

import argparse
import sys
import os
from collections import defaultdict

# 将项目根目录加入 path，以便导入 lexer.number_fsm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lexer.number_fsm import NumberFSM


def build_state_name_map() -> dict[int, str]:
    """从 NumberFSM 类常量构建 编号→名称 映射"""
    return {
        getattr(NumberFSM, attr): attr
        for attr in dir(NumberFSM)
        if attr.isupper() and isinstance(getattr(NumberFSM, attr), int)
    }


def build_category_label_map() -> dict[str, str]:
    """将 _CHAR_CATEGORY 反转成 类别→可读标签 映射"""
    cat_to_chars: dict[str, list[str]] = defaultdict(list)
    for ch, cat in NumberFSM._CHAR_CATEGORY.items():
        cat_to_chars[cat].append(ch)

    LABEL_OVERRIDES = {
        "digit": "0-9",
        "bin_digit": "0-1",
        "oct_digit": "0-7",
        "hex_letter": "a/c/f",
        "underscore": "_",
        "dot": ".",
        "quote": "'",
        "sign": "+/-",
        "bB": "b/B",
        "dD": "d/D",
        "eE": "e/E",
        "hH": "h/H",
        "oO": "o/O",
        "xX": "x/X",
    }

    result = {}
    for cat, chars in cat_to_chars.items():
        if cat in LABEL_OVERRIDES:
            result[cat] = LABEL_OVERRIDES[cat]
        else:
            # 兜底：用字符集合
            result[cat] = "".join(chars)
    return result


def make_edge_label(category: str, cat_label: dict[str, str]) -> str:
    """为转移边生成可读标签"""
    return cat_label.get(category, category)


def group_transitions(
    trans: dict[tuple[int, str], int],
) -> dict[tuple[int, int], list[str]]:
    """将 (state, cat)→next 合并为 (state, next)→[labels]"""
    grouped: dict[tuple[int, int], list[str]] = defaultdict(list)
    for (state, cat), next_state in trans.items():
        grouped[(state, next_state)].append(cat)
    return grouped


def generate_mermaid() -> str:
    """生成 Mermaid stateDiagram-v2 源码"""
    state_names = build_state_name_map()
    cat_label = build_category_label_map()
    grouped = group_transitions(NumberFSM._TRANSITIONS)

    # 接受态集合名
    accept_names = {state_names[s] for s in NumberFSM._ACCEPTING}

    lines = ["```mermaid", "stateDiagram-v2", "    direction LR"]

    # --- 起点 → 初始状态 ---
    # 数字开头
    lines.append("    [*] --> DEC_INT: 1-9")
    lines.append("    [*] --> LEADING_ZERO: 0")
    # Verilog 无位宽
    lines.append("    [*] --> AFTER_QUOTE: '")

    # --- 状态间转移 ---
    for (state, next_state), cats in sorted(grouped.items()):
        src = state_names[state]
        dst = state_names[next_state]
        labels = [make_edge_label(c, cat_label) for c in sorted(cats)]
        label = ", ".join(labels)
        lines.append(f"    {src} --> {dst}: {label}")

    # --- 接受态标记为粗框 ---
    for name in sorted(accept_names):
        lines.append(f"    {name} --> [*]")

    lines.append("```")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成 NumberFSM 的 Mermaid 状态图")
    parser.add_argument("-o", "--output", help="输出文件路径（默认输出到控制台）")
    args = parser.parse_args()

    mermaid = generate_mermaid()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid + "\n")
        print(f"已写入 {args.output}")
    else:
        print(mermaid)


if __name__ == "__main__":
    main()
