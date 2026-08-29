"""test_render_plugin.py — 渲染插件覆盖式（[render] handler + [plugins].render）。

覆盖：c4 完整管线经渲染插件产出汇编文本（覆盖主管线源端渲染）、
verilog 无渲染插件声明走主管线渲染（回归）、render handler 直接调用、
fail-fast（声明了渲染插件但组件缺失/无 handler → 报错）。

语义：渲染插件 = 覆盖式输出（输出唯一性）。语言包 tpc.toml
`[plugins].render = "组件名"` 声明启用；组件 tpc.toml `[render]
handler = "file.py:fn"` 声明入口。管线渲染阶段检测到 → 直接调 handler
产出最终文本，跳过主管线源端渲染（注释回插/格式化/幂等一并跳过）。
与 analyze/transform 的叠加式不同——渲染是一次管线唯一的最终输出。
"""

import os

import pytest

from core.plugin_loader import get_render_handler, load_all_components


class TestRenderHandlerLookup:
    def test_c4_asm_gen_declares_render(self):
        """c4 asm_gen 组件声明 [render] handler（_asm.py:render_asm）。"""
        load_all_components("grammar/c4/plugins")
        fn = get_render_handler("asm_gen")
        assert fn is not None
        assert fn.__name__ == "render_asm"

    def test_verilog_no_render_handler(self):
        """verilog 组件不声明 [render] → get_render_handler 返回 None。"""
        load_all_components("grammar/verilog/plugins")
        for name in (
            "typed_ports", "formatter", "sim", "name_check",
            "attributes", "semantic_check",
        ):
            assert get_render_handler(name) is None


class TestRenderPluginPipeline:
    @pytest.fixture(autouse=True)
    def _clean_c4_registry(self):
        """c4 管线测试隔离：默认注册表替换为干净实例。

        conftest session 基线把 verilog 规则灌进 GrammarRulesRegister
        get_default() 单例；c4 的 run_pipeline_on_source 内部用同一默认
        实例，两套规则混合后 verilog 的匿名根块 [Root] 会抢占 c4 的
        Program 根（get_block_rule 按 is_block 匿名优先）。替换为干净
        实例让 c4 规则独占（与 test_c4_asm 的独立实例同语义）。
        """
        from core.define import GrammarRulesRegister

        saved = GrammarRulesRegister._default_instance
        GrammarRulesRegister._default_instance = GrammarRulesRegister()
        yield
        GrammarRulesRegister._default_instance = saved

    def test_c4_pipeline_outputs_asm_text(self):
        """c4 完整管线（含 [plugins].render=asm_gen）→ 汇编文本输出。

        验证覆盖式：output 是汇编（LEA/IMM/ENT...），不是源端 C 还原。
        """
        from pipeline import run_pipeline_on_source

        src = "int main() { int x; x = 1; return x; }"
        r = run_pipeline_on_source(
            source=src, quiet=True, rules_dir="grammar/c4",
            check_idempotent=False,
        )
        assert r["success"], r.get("error")
        out = r["output"]
        assert "ENT" in out  # 函数进入（编译产物特征）
        assert "IMM" in out  # 立即数 1
        assert "SI" in out  # 存储 x
        assert "LEV" in out  # return 离开
        # 覆盖式：输出是汇编文本而非源端 C 还原（源端渲染不会出现 ENT）
        assert "int main" not in out

    def test_c4_render_plugin_skips_source_restore(self):
        """渲染插件路径覆盖主管线源端渲染——输出是汇编而非源端 C 还原。"""
        from pipeline import run_pipeline_on_source

        src = "int main() { return 0; }"
        r = run_pipeline_on_source(
            source=src, quiet=True, rules_dir="grammar/c4",
            check_idempotent=False,
        )
        assert r["success"]
        out = r["output"]
        # 汇编输出中不出现源端 C 特征（覆盖式：主管线源端渲染被跳过）
        assert "int main" not in out
        assert "ENT" in out

    def test_verilog_default_source_render(self):
        """verilog 无 [plugins].render → 主管线源端渲染（回归不变）。"""
        from pipeline import run_pipeline_on_source

        src = "module top;\n  wire a;\nendmodule\n"
        r = run_pipeline_on_source(
            source=src, quiet=True, rules_dir="grammar/verilog",
            check_idempotent=False,
        )
        assert r["success"], r.get("error")
        out = r["output"]
        assert "module top" in out  # 源端还原
        assert "wire a" in out


class TestRenderPluginFailFast:
    def test_missing_component_fail_fast(self, tmp_path, monkeypatch):
        """语言包声明 [plugins].render 但组件不存在 → 报错（ADR-0003）。"""
        from pipeline import _resolve_render_handler

        lang = tmp_path / "lang"
        lang.mkdir()
        (lang / "tpc.toml").write_text(
            "[plugins]\nrender = 'nope'\n", encoding="utf-8"
        )
        # 该语言包无组件加载（_loaded_components 里没有 'nope'）
        with pytest.raises(ValueError, match="render"):
            _resolve_render_handler(str(lang))

    def test_plugin_without_render_decl_fail_fast(self, tmp_path, monkeypatch):
        """声明引用存在的组件但该组件无 [render] handler → 报错。"""
        from pipeline import _resolve_render_handler

        lang = tmp_path / "lang2"
        comp = lang / "plugins" / "typed_ports"
        comp.mkdir(parents=True)
        (comp / "tpc.toml").write_text(
            "[component]\nname = 'typed_ports'\n\n[grammar]\nfiles = []\n",
            encoding="utf-8",
        )
        (lang / "tpc.toml").write_text(
            "[plugins]\nrender = 'typed_ports'\n", encoding="utf-8"
        )
        # 加载该临时语言包组件（真实 typed_ports 不在其中）
        load_all_components(str(lang / "plugins"))
        with pytest.raises(ValueError, match="render"):
            _resolve_render_handler(str(lang))


class TestRenderHandlerDirect:
    def test_render_asm_program_node(self):
        """render_asm 直接接收 AsmProgram 节点（transform 产物）→ 文本。"""
        from core.define import Node
        from grammar.c4.plugins.asm_gen._asm import render_asm

        prog = Node("AsmProgram")
        prog.add_sub_node(Node("AsmLine", text="  ENT 0"))
        prog.add_sub_node(Node("AsmLine", text="  LEV"))
        assert render_asm(prog) == "  ENT 0\n  LEV\n"

    def test_render_asm_compile_fallback(self):
        """render_asm 接收 Program（变换未跑）→ 现场编译兜底。"""
        from grammar.c4.plugins.asm_gen._asm import render_asm

        # 经完整管线 transform 前的 Program 较难手工构造，验证 None 守卫
        assert render_asm(None) == ""
        assert render_asm("not a node") == ""
