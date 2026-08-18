"""Lexer utilities: TOML config loading and merging.

配置通过 ConfigRegistry 声明式加载，不再内部 try/except 吞错误。
"""

import os
import tomllib
from core.define import FileManager


def merge_token_define(resolved: dict) -> dict:
    """从已解析配置 dict 合并 token 定义（基础 + 语言覆盖 + 增强层覆盖）。

    resolved: ConfigRegistry.resolve() 的返回（含 "lexer.token_base" 等 key）。
    """
    base = dict(resolved.get("lexer.token_base", {}))
    base = _deep_merge(base, dict(resolved.get("lexer.lexer_base", {})))
    if resolved.get("lexer.token_lang"):
        base = _deep_merge(base, dict(resolved["lexer.token_lang"]))
    if resolved.get("lexer.token_ext"):
        base = _deep_merge(base, dict(resolved["lexer.token_ext"]))
    _validate_token_define(base)
    return base


def extract_number_configs(raw: dict) -> list[dict]:
    """从 lexer.number 配置提取 [[number.based]] 形态列表。"""
    based = raw.get("based", [])
    if isinstance(based, list):
        return [b for b in based if isinstance(b, dict)]
    return []


def get_number_config(rules_dir: str | None = None) -> list[dict]:
    """读取数字形态声明（lexer.number），供 number_gen 编译。

    rules_dir 指定时按该语言包解析（跟随语言包，不依赖全局 _loaded 状态）；
    None 时读全局已加载配置（无 rules_dir 的旧路径）。

    Returns: [[number.based]] 形态列表（空 = 使用默认/不启用配置化数字）。
    """
    from core.config_registry import ConfigRegistry

    if rules_dir:
        raw = ConfigRegistry.resolve(
            rules_dir, plugins_dir=os.path.join(rules_dir, "plugins")
        ).get("lexer.number", {}) or {}
    else:
        try:
            raw = ConfigRegistry.get("lexer.number") or {}
        except (RuntimeError, KeyError):
            raw = {}
    return extract_number_configs(raw)


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

    按 rules_dir 从 ConfigRegistry.resolve 解析（不依赖全局 _loaded 状态），
    保证 Lexer 实例的配置跟随其语言包——同一进程跨语言时不会串用上一次
    load_all 的语言配置。
    """
    from core.config_registry import ConfigRegistry

    resolved = ConfigRegistry.resolve(
        rules_dir,
        ext_dirs=ext_dirs,
        plugins_dir=os.path.join(rules_dir, "plugins"),
    )
    return merge_token_define(resolved)


def _validate_token_define(td: dict) -> None:
    """token 配置结构性自检（简单校验，fail-fast）。

    防护"配置加载失败被静默吞掉 → 空表 → 全部 token 退化为 id"的静默错乱
    （2026-08-09 token.toml 重复 key 事故：整个 [id.keyword] 表丢失后，
    module/always/begin 全被当普通 id，linter/parser 全面静默错乱）。

    只校验 lexer 硬依赖的关键段存在 + 关键字表非空——不校验具体关键字内容
    （语言无关，只拦"结构性退化"）。
    """
    missing = [s for s in ("symbol", "space", "newline", "bracket", "id") if s not in td]
    if missing:
        raise RuntimeError(
            "[lexer] token 配置缺少关键段: " + ", ".join(missing)
            + "（检查 grammar 下 base/_token.toml 与 token.toml 是否损坏）"
        )
    kw = (td.get("id") or {}).get("keyword") or {}
    if not isinstance(kw, dict) or not kw:
        raise RuntimeError(
            "[lexer] token 配置的 [id.keyword] 缺失或为空——关键字表为空会导致"
            "全部标识符退化为 id（静默错乱）。检查 token.toml 关键字定义是否完整。"
        )



