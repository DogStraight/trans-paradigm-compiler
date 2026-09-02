# grammar 包标记（空文件）
#
# 让 grammar/ 成为 Python 包，使语法 TOML 能作为 package-data 随 wheel
# 分发并保留目录结构（data-files 会扁平化多语言包，不可用）。
# pyproject.toml [tool.setuptools.packages.find] include 含 "grammar*"，
# 删除本文件会导致语法包不再随 wheel 分发——不可删。
