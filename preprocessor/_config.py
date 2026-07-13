"""Preprocessor config loader — reads base/_macro.toml via ConfigRegistry."""

from core.config_registry import config


def load_macro_config(rules_dir: str) -> dict:
    """从 ConfigRegistry 获取宏配置。"""
    try:
        return dict(config.get("preprocessor.macro_config"))
    except KeyError:
        return {}
