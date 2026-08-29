"""test_plugin_cluster.py — 插件聚类目录（用户自定义分类，引擎不规定枚举）。

覆盖：discover_components 递归发现（任意深度聚类目录）、重名组件 fail-fast、
discover_rule_files 递归发现 rules/*.toml、config_registry 插件配置声明
递归查找（_find_plugin_tpc + 相对路径前缀）、load_all_components 加载
聚类组件、真实 verilog 平铺结构兼容（回归）。

聚类约定：plugins/ 下任意深度子目录均可作为分类容器（如
plugins/checks/name_check），任何含**有效组件声明**（[grammar]/[analyzer]/
[transform]/[pipeline]/[capabilities] 之一非空）的 tpc.toml 目录是一个
组件；纯 rules 目录（空 tpc.toml + rules/*.toml，如真实 name_check）不
是组件，由 check_registry 独立递归发现。引擎不规定分类名枚举。
"""

import os

import pytest

from core._protocol import META_NAME
from core.plugin_loader import (
    _parse_component_toml,
    discover_components,
    get_component_grammar_files,
    load_all_components,
)


def _make_cluster_tree(tmp_path, with_dup: bool = False):
    """构造聚类插件树（组件名用 clu_ 前缀，避免与 verilog 真实组件名
    冲突——load_component 按名缓存，重名会串到 verilog 组件）：

    plugins/
      checks/
        clu_namecheck/        # 纯规则组件（空 tpc.toml + rules/，同真实）
          tpc.toml            # 全注释 = 空声明（非组件）
          rules/naming.toml
      syntax/
        clu_sim/              # 语法组件（[grammar] files）
          tpc.toml
          00_sim.toml
      _private/               # 私有目录（_ 前缀，跳过）
        tpc.toml
      orphan/                 # 分类容器（无 tpc.toml，跳过）
    """
    plugins = tmp_path / "plugins"
    name_check = plugins / "checks" / "clu_namecheck"
    name_check.mkdir(parents=True)
    (name_check / "tpc.toml").write_text(
        "# clu_namecheck — 纯规则组件（空声明，同真实 name_check）\n",
        encoding="utf-8",
    )
    rules = name_check / "rules"
    rules.mkdir()
    (rules / "naming.toml").write_text(
        "[[checks]]\nid = 'CLU001'\ncategory = 'naming'\n"
        "severity = 'warning'\nkind = 'module'\nmessage = 'm'\n",
        encoding="utf-8",
    )

    sim = plugins / "syntax" / "clu_sim"
    sim.mkdir(parents=True)
    (sim / "tpc.toml").write_text(
        "[component]\nname = 'clu_sim'\nlang = 'c4'\n\n[grammar]\nfiles = ['00_sim.toml']\n",
        encoding="utf-8",
    )
    (sim / "00_sim.toml").write_text(
        "[SimExtra]\nproduction = 'SimExtra : ;'\n", encoding="utf-8"
    )

    priv = plugins / "_private"
    priv.mkdir()
    (priv / "tpc.toml").write_text(
        "[component]\nname = 'priv'\n", encoding="utf-8"
    )

    orphan = plugins / "orphan"
    orphan.mkdir()

    if with_dup:
        dup = plugins / "checks" / "dup" / "clu_sim"
        dup.mkdir(parents=True)
        (dup / "tpc.toml").write_text(
            "[component]\nname = 'clu_sim'\n", encoding="utf-8"
        )
    return plugins


class TestDiscoverComponents:
    def test_recursive_cluster_discovery(self, tmp_path):
        plugins = _make_cluster_tree(tmp_path)
        metas = discover_components(str(plugins))
        names = sorted(m[META_NAME] for m in metas)
        # 仅 clu_sim 是组件（clu_namecheck 空声明非组件；_private/orphan 跳过）
        assert names == ["clu_sim"]
        assert metas[0]["_dir"].endswith(os.path.join("syntax", "clu_sim"))

    def test_duplicate_name_fail_fast(self, tmp_path):
        plugins = _make_cluster_tree(tmp_path, with_dup=True)
        with pytest.raises(ValueError, match="Component name conflict"):
            discover_components(str(plugins))

    def test_flat_layout_still_discovered(self, tmp_path):
        """平铺布局（plugins/<name>/）仍被发现——回归兼容。"""
        flat = tmp_path / "flat"
        comp = flat / "flatplug"
        comp.mkdir(parents=True)
        (comp / "tpc.toml").write_text(
            "[component]\nname = 'flatplug'\n\n[grammar]\nfiles = ['00_f.toml']\n",
            encoding="utf-8",
        )
        (comp / "00_f.toml").write_text(
            "[FlatRule]\nproduction = 'FlatRule : ;'\n", encoding="utf-8"
        )
        metas = discover_components(str(flat))
        assert [m[META_NAME] for m in metas] == ["flatplug"]


class TestDiscoverRuleFiles:
    def test_recursive_rules_discovery(self, tmp_path):
        from core.check_registry import discover_rule_files, load_check_rules

        plugins = _make_cluster_tree(tmp_path)
        files = discover_rule_files(str(plugins))
        # 聚类后 rules/ 位于 checks/name_check/rules/，仍被递归发现
        assert len(files) == 1
        assert files[0].endswith(os.path.join("rules", "naming.toml"))

        rules = load_check_rules(str(plugins))
        assert {r["id"] for r in rules} == {"CLU001"}

    def test_flat_rules_still_discovered(self, tmp_path):
        from core.check_registry import discover_rule_files

        rules = tmp_path / "plugins2" / "plug" / "rules"
        rules.mkdir(parents=True)
        (rules / "r.toml").write_text(
            "[[checks]]\nid = 'FL001'\ncategory = 'x'\nseverity = 'info'\n"
            "kind = 'wire'\nmessage = 'm'\n",
            encoding="utf-8",
        )
        files = discover_rule_files(str(tmp_path / "plugins2"))
        assert len(files) == 1 and files[0].endswith(os.path.join("rules", "r.toml"))


class TestPluginConfigDeclarations:
    def test_find_plugin_tpc_recursive(self, tmp_path):
        from core.config_registry import _find_plugin_tpc

        plugins = _make_cluster_tree(tmp_path)
        tpc, rel = _find_plugin_tpc(str(tmp_path), "clu_sim")
        assert tpc.endswith(os.path.join("syntax", "clu_sim", "tpc.toml"))
        assert rel == "syntax/clu_sim"

    def test_missing_plugin_returns_empty(self, tmp_path):
        from core.config_registry import _find_plugin_tpc

        tpc, rel = _find_plugin_tpc(str(tmp_path), "nope")
        assert tpc == "" and rel == ""


class TestLoadClusteredComponents:
    def test_load_from_cluster_tree(self, tmp_path):
        plugins = _make_cluster_tree(tmp_path)
        infos = load_all_components(str(plugins))
        names = {i["name"] for i in infos}
        assert names == {"clu_sim"}
        assert infos[0]["grammar_files"] == [
            os.path.join(str(plugins), "syntax", "clu_sim", "00_sim.toml")
        ]

    def test_get_component_grammar_files_clustered(self, tmp_path):
        plugins = _make_cluster_tree(tmp_path)
        load_all_components(str(plugins))
        files = get_component_grammar_files()
        assert any(
            os.path.join("syntax", "clu_sim", "00_sim.toml") in f for f in files
        )


class TestVerilogFlatRegression:
    def test_verilog_components_discovered(self):
        """verilog 现有平铺组件在递归发现下不受影响（含真实 name_check
        空声明组件——它不在组件表，规则走 check_registry）。"""
        from core.define import DEFAULT_RULES_DIR

        plugins_dir = os.path.join(DEFAULT_RULES_DIR, "plugins")
        metas = discover_components(plugins_dir)
        names = {m[META_NAME] for m in metas}
        for expect in (
            "attributes",
            "configs",
            "formatter",
            "gates",
            "inst_check",
            "nettypes",
            "semantic_check",
            "sim",
            "specify",
            "typed_ports",
            "udp",
        ):
            assert expect in names, f"组件 {expect} 未被递归发现"
        # 空声明组件（name_check）不在组件表
        assert "name_check" not in names

    def test_parse_component_toml_basename(self, tmp_path):
        """_parse_component_toml 的 name 来自目录 basename（聚类后不变）。"""
        deep = tmp_path / "a" / "b" / "comp"
        deep.mkdir(parents=True)
        (deep / "tpc.toml").write_text(
            "[component]\nname = 'comp'\n\n[grammar]\nfiles = ['00_x.toml']\n",
            encoding="utf-8",
        )
        (deep / "00_x.toml").write_text(
            "[XRule]\nproduction = 'XRule : ;'\n", encoding="utf-8"
        )
        meta = _parse_component_toml(str(deep / "tpc.toml"))
        assert meta["name"] == "comp"
