"""formatter 能力入口（P2.5 插件回调能力化）。

pipeline 不再直接 import grammar.verilog 插件；组件通过 tpc.toml
[capabilities] 声明能力入口，引擎按能力名查找
（core/plugin_loader.py::get_capability）。

本模块用绝对导入：_load_python_handlers 以 spec_from_file_location
加载，无包上下文、不支持相对导入（与 typed_ports 模块同风格）。

Doc: docs/component_protocol.md（组件协议：[capabilities] 段）
"""

from grammar.verilog.plugins.formatter import (
    build_engine,
    split_inst_tail_lines,
    split_port_close_lines,
)
from grammar.verilog.plugins.formatter.boundary import BoundaryScanner


def build_formatter() -> dict:
    """返回 formatter 能力 API 面（pipeline format_generated 消费）。"""
    return {
        "BoundaryScanner": BoundaryScanner,
        "build_engine": build_engine,
        "split_port_close_lines": split_port_close_lines,
        "split_inst_tail_lines": split_inst_tail_lines,
    }
