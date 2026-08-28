"""attribution.py — 署名单一来源（打包管线与 --credits 共用）。

打包管线（build_pipeline.py）生成入口时烘焙这些常量进 exe：
    - PE 版本资源（--company-name/--copyright，strings -el 可扫）
    - --credits 输出
修改作者/邮箱/仓库只需改这里，然后重新打包。
"""

AUTHOR_NAME = "biominescence"  # 笔名；GitHub 账号为 DogStraight
AUTHOR_EMAIL = "oho15799293498@outlook.com"
# AI 协作者（模型辅助开发，0.1.0 起署名）：本项目的语法包/引擎/验证
# 大量由 deepseek-v4-flash 协作完成，正式列入署名。
AI_CO_AUTHOR = "deepseek-v4-flash"
REPO_URL = "https://github.com/DogStraight/trans-paradigm-compiler"
LICENSE = "MIT"


def credits_text(prog: str, version: str) -> str:
    return (
        f"{prog} {version} — TransParadigm Verilog toolchain\n"
        f"Author: {AUTHOR_NAME} <{AUTHOR_EMAIL}>\n"
        f"AI Co-author: {AI_CO_AUTHOR}\n"
        f"Source: {REPO_URL}\n"
        f"License: {LICENSE}\n"
        f"Implementation: core engine, grammar packages and verification\n"
        f"  suites co-developed with {AI_CO_AUTHOR} (AI co-author).\n"
    )
