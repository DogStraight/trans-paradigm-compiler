"""attribution.py — 署名单一来源（打包管线与 --credits 共用）。

打包管线（build_pipeline.py）生成入口时烘焙这些常量进 exe：
    - PE 版本资源（--company-name/--copyright，strings -el 可扫）
    - --credits 输出
修改作者/邮箱/仓库只需改这里，然后重新打包。
"""

AUTHOR_NAME = "biominescence"
AUTHOR_EMAIL = "oho15799293498@outlook.com"
REPO_URL = "https://github.com/biominescence"
LICENSE = "MIT"


def credits_text(prog: str, version: str) -> str:
    return (
        f"{prog} {version} — TransParadigm Verilog toolchain\n"
        f"Author: {AUTHOR_NAME} <{AUTHOR_EMAIL}>\n"
        f"Source: {REPO_URL}\n"
        f"License: {LICENSE}\n"
    )
