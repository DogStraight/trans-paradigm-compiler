"""ConfigRegistry — 声明式配置注册中心。

用法:
    # 1. 在管线启动点统一加载
    from core.config_registry import ConfigRegistry
    ConfigRegistry.load_all(rules_dir, ext_dirs=ext_dirs)

    # 2. 使用（key 常量定义在 core/config_map.py）
    from core.config_map import PRATT_TOKEN_CATEGORIES
    cats = config.get(PRATT_TOKEN_CATEGORIES)

所有 config.declare() 声明集中在 core/config_map.py 中。
"""

import os
import tomllib
from typing import Any


class ConfigRegistry:
    """配置注册中心。"""

    _entries: dict[str, dict] = {}
    _loaded: dict[str, Any] = {}
    _resolved: bool = False

    @classmethod
    def declare(
        cls,
        name: str,
        *,
        file: str,
        section: str | None = None,
        required: bool = True,
        base: str = "rules",
        description: str = "",
    ) -> None:
        """声明一个配置依赖。

        Args:
            name: 配置唯一标识名（命名空间风格，如 "pratt.token_categories"）
            file: TOML 文件路径（相对 base 目录）
            section: TOML 中的 section key，None 表示整个文件内容
            required: 加载失败是否致命（True=崩溃，False=静默返回空 dict）
            base: 基准目录名，对应 load_all() 的 **base_dirs 参数中的 key
            description: 人类可读描述（用于错误信息）
        """
        if name in cls._entries:
            return  # 重复声明安全无害
        cls._entries[name] = {
            "file": file,
            "section": section,
            "required": required,
            "base": base,
            "description": description,
        }

    @classmethod
    def load_all(
        cls, rules_dir: str, ext_dirs: list[str] | None = None, **base_dirs: str
    ) -> None:
        """加载所有已声明的配置。

        每个声明的 file 路径根据其 base 参数选基准目录拼接：
        - base="rules" 用 rules_dir（默认）
        - base="ext" 用 ext_dirs[0]（兼容单层 EXT）
        - base="ext_N" 用 ext_dirs[N]（多层 EXT）
        - 自定义 base 名 → 从 **base_dirs 取对应 key

        对所有 required=True 的声明：加载失败抛 RuntimeError，列出所有错误。
        对所有 required=False 的声明：加载失败静默存空 dict。
        """
        from core.define import FileManager

        # 基准目录表
        bases: dict[str, str] = {"rules": rules_dir}
        ext_list = list(ext_dirs) if ext_dirs else []
        for i, d in enumerate(ext_list):
            bases[f"ext_{i}"] = d
        if ext_list:
            bases["ext"] = ext_list[0]  # 兼容 base="ext"
        else:
            bases["ext"] = ""  # ext 为空，required=False 的声明静默失败
        for bk, bv in base_dirs.items():
            # 去掉 _dir 后缀便于匹配
            key = bk.removesuffix("_dir")
            bases[key] = bv

        cls._loaded.clear()
        errors: list[str] = []

        for name, spec in cls._entries.items():
            base_key = spec.get("base", "rules")
            base_dir = bases.get(base_key)
            if base_dir is None:
                errors.append(f"  [{name}] base='{base_key}' 未在 load_all() 中提供")
                continue

            try:
                path = os.path.join(base_dir, spec["file"]).replace("\\", "/")
                content = FileManager.read_file(path)
                data = tomllib.loads(content)

                if spec["section"]:
                    data = data.get(spec["section"], {})

                cls._loaded[name] = data

            except Exception as e:
                if spec["required"]:
                    loc = f"{base_key}:{spec['file']}"
                    if spec["section"]:
                        loc += f" → [{spec['section']}]"
                    errors.append(f"  [{name}] {loc}: {e}")
                else:
                    cls._loaded[name] = {}

        if errors:
            raise RuntimeError(
                "[ConfigRegistry] 以下配置加载失败：\n"
                + "\n".join(errors)
                + "\n\n请检查规则目录结构和 TOML 文件内容。"
            )

        cls._resolved = True

    @classmethod
    def get(cls, name: str) -> Any:
        """获取已加载的配置值。

        在 load_all() 之前调用抛 RuntimeError（防止隐式依赖）。
        required=False 的声明在加载失败时返回空 dict。
        """
        if not cls._resolved:
            raise RuntimeError(
                f"[ConfigRegistry] get('{name}') 在 load_all() 之前被调用——"
                f"配置尚未加载。请确保管线入口先调用 load_all()。"
            )
        if name not in cls._loaded:
            raise KeyError(
                f"[ConfigRegistry] '{name}' 未声明。可用声明: {list(cls._entries.keys())}"
            )
        return cls._loaded[name]

    @classmethod
    def reset(cls) -> None:
        """重置注册表（测试用）。"""
        cls._entries.clear()
        cls._loaded.clear()
        cls._resolved = False


# 模块级单例（简化 import）
config = ConfigRegistry

# 加载配置声明（在 ConfigRegistry 定义之后，确保 import 安全）
from core import config_map  # noqa: F401

# 自动安装配置声明
config_map.install()
