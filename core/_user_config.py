"""core/_user_config.py — 用户项目配置定位（单一实现）。

Search order:
    1. $TPC_CONFIG env var (explicit override)
    2. From CWD upward: config/tpc_config.json
    3. Global fallback: ""

历史：_find_user_config 曾在 core/define.py 与 core/config_registry.py 各有一份
（避免循环导入）。现抽到本独立小文件（仅依赖 os，无循环风险），两处统一导入。
"""

import os

_CONFIG_CANDIDATES = ["config/tpc_config.json"]


def find_user_config() -> str:
    """查找用户项目配置文件（tpc_config.json），未找到返回空字符串。"""
    # 1. Env var override
    env_path = os.environ.get("TPC_CONFIG")
    if env_path:
        path = os.path.abspath(env_path)
        if os.path.isfile(path):
            return path

    # 2. Walk up from CWD
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

    # 3. Global fallback
    return ""
