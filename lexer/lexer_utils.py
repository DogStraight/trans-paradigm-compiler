"""Lexer utilities: TOML config loading and merging.

配置通过 ConfigRegistry 声明式加载，不再内部 try/except 吞错误。
"""

import tomllib
from core.define import FileManager
from core.config_registry import declare_cfg

# ── 配置需求（来自 pyv.toml） ──────────────────────────
# lexer.token_base
#   #sym:config = (root)
#   格式: dict — { "token_name": { type, pattern }, ... }
_token_base_cfg: dict = declare_cfg("lexer.token_base", {}, __name__, "_token_base_cfg")

# lexer.lexer_base
#   #sym:config = (root)
#   格式: dict — { "state_name": [{ type, pattern, token }, ...], ... }
_lexer_base_cfg: dict = declare_cfg("lexer.lexer_base", {}, __name__, "_lexer_base_cfg")

# lexer.token_lang
#   #sym:config = (root)
#   格式: dict — 语言专用 token 覆盖（可选）
_token_lang_cfg: dict = declare_cfg("lexer.token_lang", {}, __name__, "_token_lang_cfg")

# lexer.token_ext
#   #sym:config = (root)
#   格式: dict — 增强层 token 覆盖（可选）
_token_ext_cfg: dict = declare_cfg("lexer.token_ext", {}, __name__, "_token_ext_cfg")
def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 到 base，override 的值优先"""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_token_define(base_dir: str = "") -> dict:
    """（向后兼容）直接读取 token.toml 文件。新代码应使用 ConfigRegistry。"""
    if not base_dir:
        base_dir = FileManager.token_define_file
    token_content = FileManager.read_file(base_dir)
    return tomllib.loads(token_content)


def get_token_define_merged(rules_dir: str, ext_dirs: list[str] | None = None) -> dict:
    """加载 token 定义：基础定义 + 语言覆盖 + 增强层覆盖。

    替代旧的路径拼接 + try/except 模式。
    """
    base = dict(_token_base_cfg)
    base = _deep_merge(base, dict(_lexer_base_cfg))
    if _token_lang_cfg:
        base = _deep_merge(base, dict(_token_lang_cfg))
    if _token_ext_cfg:
        base = _deep_merge(base, dict(_token_ext_cfg))
    return base


def semicolon_token_type() -> str:
    """从 lexer.token_base 推导分号 token 类型（配置驱动，不硬编码）。

    分号定义在 [symbol.base]（如 semicolon = ";"），lexer 按 symbol.{cat}.{name}
    命名，推导得到 "symbol.base.semicolon"。换语言时自动适配，避免硬编码失效。
    """
    for name in _token_base_cfg.get("symbol", {}).get("base", {}):
        if name == "semicolon":
            return f"symbol.base.{name}"
    raise RuntimeError("lexer.token_base 缺少 semicolon 符号定义")
