"""core/_user_config.py — 用户项目配置定位（单一实现）。

Search order:
    1. $TPC_CONFIG env var (explicit override)
    2. From CWD upward: config/tpc_config.json   (workspace-local profile)
    3. ~/.tpc/config.json                         (global profile)
    4. Global fallback: ""

历史：_find_user_config 曾在 core/define.py 与 core/config_registry.py 各有一份
（避免循环导入）。现抽到本独立小文件（仅依赖 os，无循环风险），两处统一导入。

全局 profile（~/.tpc/config.json）：提供"一次配置、任意工作区自动享用"的用户级
默认（工作区/环境仍可覆盖）。新实例启动时按上述顺序自动发现。
Doc: docs/config_lifecycle.md（用户配置定位）
"""

import os

_CONFIG_CANDIDATES = ["config/tpc_config.json"]

# 全局 profile（用户级默认，跨工作区共享；工作区 config 与 $TPC_CONFIG 优先）
_GLOBAL_CONFIG = os.path.join(os.path.expanduser("~"), ".tpc", "config.json")


def find_user_config() -> str:
    """查找用户项目配置文件（tpc_config.json），未找到返回空字符串。

    优先级：$TPC_CONFIG 显式 > CWD 向上（工作区隔离）> ~/.tpc/config.json（全局）。
    """
    # 1. Env var override
    env_path = os.environ.get("TPC_CONFIG")
    if env_path:
        path = os.path.abspath(env_path)
        if os.path.isfile(path):
            return path

    # 2. Walk up from CWD (workspace-local profile)
    cwd = os.path.abspath(os.getcwd())
    parent = cwd
    while True:
        for name in _CONFIG_CANDIDATES:
            path = os.path.join(parent, name)
            if os.path.isfile(path):
                return path
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent

    # 3. Global profile (~/.tpc/config.json)
    if os.path.isfile(_GLOBAL_CONFIG):
        return _GLOBAL_CONFIG

    # 4. Global fallback
    return ""
