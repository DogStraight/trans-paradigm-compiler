# grammar 包标记（空文件）
#
# 让 grammar/ 成为 Python 包，使语法 TOML 能作为 package-data 随 wheel 分发
# 并保留目录结构（data-files 会扁平化多语言包，不可用）。
# 语法 TOML 仍是独立外置资产——本文件不承载任何逻辑，可单独 fork 时删除。
