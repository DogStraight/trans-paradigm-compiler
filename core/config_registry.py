"""ConfigRegistry — 声明式配置注册中心。

问题：当前各模块在内部直接读 TOML 文件，路径解析各自为政，
失败时静默返回空值，没人知道配置挂了。

方案：所有配置依赖必须在模块级别通过 declare() 声明，
启动时由 load_all() 统一加载验证。required 声明加载失败 → RuntimeError，
optional 声明加载失败 → 空 dict，不再有隐式的 try/except 吞错误。

用法:
    # 1. 在组件模块级别声明
    from core.config_registry import config
    config.declare(
        "pratt.token_categories",
        file="base/_lexer.toml",
        section="token_category")

    # 2. 管线启动点统一加载
    ConfigRegistry.load_all(rules_dir, ext_dir="path/to/ext")

    # 3. 使用
    cats = config.get("pratt.token_categories")
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
    def load_all(cls, rules_dir: str, **base_dirs: str) -> None:
        """加载所有已声明的配置。

        每个声明的 file 路径根据其 base 参数选基准目录拼接：
        - base="rules" 用 rules_dir（默认）
        - base="ext" 用 base_dirs["ext_dir"]
        - 自定义 base 名 → 从 **base_dirs 取对应 key

        对所有 required=True 的声明：加载失败抛 RuntimeError，列出所有错误。
        对所有 required=False 的声明：加载失败静默存空 dict。
        """
        from core.define import FileManager

        # 基准目录表
        bases: dict[str, str] = {"rules": rules_dir}
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
    def is_declared(cls, name: str) -> bool:
        """检查是否已声明某个配置"""
        return name in cls._entries

    @classmethod
    def registered_sources(cls) -> list[dict]:
        """返回所有声明的摘要（用于调试/检查）"""
        return [{"name": n, **s} for n, s in cls._entries.items()]

    @classmethod
    def reset(cls) -> None:
        """重置注册表（测试用）。"""
        cls._entries.clear()
        cls._loaded.clear()
        cls._resolved = False


# 模块级单例（简化 import）
config = ConfigRegistry
