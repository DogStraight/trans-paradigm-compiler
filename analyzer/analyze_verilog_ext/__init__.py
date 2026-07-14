"""analyze_verilog_ext/ — Verilog 专用分析扩展

自动发现并注册所有 _*.py 模块中的 analyzer primitive，
并导出映射表配置供 transform 使用。

外部管线只需 import 本包，无需逐个 import 子模块：

    import analyzer.analyze_verilog_ext  # 注册原语 + 映射表就绪
"""

import importlib
import pkgutil

# 自动加载所有 _*.py 模块（通过 @register 注册原语）
for _imp, modname, _ in pkgutil.iter_modules(__path__):
    if modname.startswith("_") and modname != "__init__":
        importlib.import_module(f"{__name__}.{modname}")

# 导出映射表配置（供 SemanticMappingPlugin 消费）
from ._mapping import mapping_entries, resolve_entries, collect_callbacks

__all__ = ["mapping_entries", "resolve_entries", "collect_callbacks"]
