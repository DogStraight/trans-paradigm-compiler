"""配置加载防护单元测试 — malformed TOML / 缺段 / 可选缺失。

固化 token.toml 重复 key 事故的防护契约：
    - required=False 的文件，TOML 语法损坏（重复 key 等）→ ConfigError（fail-fast，
      不能再静默退化成空表导致"全部 token 变 id"的静默错乱）
    - 文件存在但缺声明的 section → ConfigError（配置声明错误）
    - 可选文件缺失 → 容忍（合法的可选缺失）
"""

import os

import pytest

from core.errors import ConfigError
from core.config_registry import ConfigRegistry, _load_meta_declarations

pytestmark = pytest.mark.smoke  # smoke：core 组代表（配置 fail-fast 契约）


@pytest.fixture
def isolated_registry(tmp_path):
    """隔离 ConfigRegistry：reset 后测试自行声明/加载。

    不再手动 save/restore（旧 workaround 只还原 _entries/_loaded/_resolved
    三字段，漏 _entries_source，且与 conftest 的 autouse 全局还原机制时序
    交错导致状态残留）；全局还原由 core/global_state.py 机制兜底——
    每个测试结束后自动还原到 verilog 基线。
    """
    ConfigRegistry.reset()
    yield tmp_path


def _declare_and_load(
    root,
    name,
    fname,
    *,
    section=None,
    required=False,
):
    ConfigRegistry.declare(
        name, file=fname, section=section, required=required, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))


def test_malformed_toml_fails_fast_even_optional(isolated_registry):
    """可选文件（required=False）含重复 key → ConfigError（incident 场景）。"""
    root = isolated_registry
    (root / "bad_dup.toml").write_text(
        '[id.keyword]\nmodule = "module"\nmodule = "module"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="TOML 语法错误"):
        _declare_and_load(root, "t.baddup", "bad_dup.toml", required=False)


def test_missing_declared_section_fails_fast(isolated_registry):
    """文件存在但缺声明的 section → ConfigError（不再静默 data.get(section, {})）。"""
    root = isolated_registry
    (root / "bad_section.toml").write_text('[other]\nx = 1\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="缺少声明段"):
        _declare_and_load(
            root, "t.badsect", "bad_section.toml", section="missing_sec", required=False
        )


def test_optional_missing_file_tolerated(isolated_registry):
    """可选文件缺失是合法状态 → 容忍，加载为空 dict，不报错。"""
    root = isolated_registry
    ConfigRegistry.declare(
        "t.okmissing", file="nope.toml", required=False, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._loaded.get("t.okmissing") == {}


def test_required_missing_file_fails_fast(isolated_registry):
    """必选文件缺失 → ConfigError（原有契约保持）。"""
    root = isolated_registry
    with pytest.raises(ConfigError, match="No such file|未找到|找不到"):
        _declare_and_load(root, "t.reqmiss", "nope.toml", required=True)


# ── 来源追踪（config dump 基础） ──────────────────────────


def test_sources_recorded_on_load(isolated_registry):
    """load_all 后 _sources 记录每个 key 的实际文件 + section。"""
    root = isolated_registry
    (root / "src.toml").write_text(
        '[number]\nbased = [1, 2]\n[other]\nx = 1\n', encoding="utf-8"
    )
    ConfigRegistry.declare(
        "t.src1", file="src.toml", section="number", required=True, base="temp"
    )
    ConfigRegistry.declare(
        "t.src2", file="src.toml", required=True, base="temp"
    )
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._sources["t.src1"] == {
        "file": str(root / "src.toml").replace("\\", "/"),
        "section": "number",
    }
    assert ConfigRegistry._sources["t.src2"]["section"] is None


def test_sources_bare_and_missing(isolated_registry):
    """bare data 与缺失文件在 sources 中正确标记。"""
    root = isolated_registry
    ConfigRegistry.declare("t.bare", file="", bare_value=[1, 2, 3])
    ConfigRegistry.declare("t.miss", file="nope.toml", required=False, base="temp")
    ConfigRegistry.load_all(root, temp_dir=str(root))
    assert ConfigRegistry._sources["t.bare"] == {"bare": True}
    assert ConfigRegistry._sources["t.miss"]["missing"] is True


def test_resolve_with_sources_returns_pair(isolated_registry):
    """resolve_with_sources 返回 (loaded, sources)，resolve 保持返回 dict。"""
    root = isolated_registry
    (root / "r.toml").write_text('[sec]\na = 1\n', encoding="utf-8")
    ConfigRegistry.declare(
        "t.r", file="r.toml", section="sec", required=True, base="temp"
    )
    loaded, sources = ConfigRegistry.resolve_with_sources(
        str(root), temp_dir=str(root)
    )
    assert loaded["t.r"] == {"a": 1}
    assert sources["t.r"]["section"] == "sec"
    # resolve 兼容：仍返回 dict
    r = ConfigRegistry.resolve(str(root), temp_dir=str(root))
    assert isinstance(r, dict)


# ── 声明结构校验（schema 化第一步） ──────────────────────


def _write_tpc(tmp_path, content):
    (tmp_path / "tpc.toml").write_text(content, encoding="utf-8")


def test_decl_unknown_field_rejected(tmp_path):
    """声明含未知字段 → ConfigError（fail-fast）。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = "x.toml", typo = 1 }\n')
    with pytest.raises(ConfigError, match="未知字段"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_missing_file_rejected(tmp_path):
    """dict 含声明字段但缺 file → ConfigError（疑似忘了 file）。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { section = "x" }\n')
    with pytest.raises(ConfigError, match="缺 file"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_file_type_rejected(tmp_path):
    """file 类型错误（非 str/list）→ ConfigError。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = 123 }\n')
    with pytest.raises(ConfigError, match="file 必须是字符串"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_required_type_rejected(tmp_path):
    """required 类型错误（非 bool）→ ConfigError。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = "x.toml", required = "yes" }\n')
    with pytest.raises(ConfigError, match="required 必须是布尔值"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def test_decl_valid_bare_and_file_accepted(tmp_path):
    """合法 bare data 与文件式声明通过校验。"""
    _write_tpc(
        tmp_path,
        '[analyzer]\nprimitives = ["a", "b"]\n'
        '[lexer]\nok = { file = "x.toml", section = "s", required = false }\n',
    )
    decls = _load_meta_declarations(grammar_dir=str(tmp_path))
    names = [d[0] for d in decls]
    assert "analyzer.primitives" in names
    assert "lexer.ok" in names


# ── 声明级合并语义 `merge = "by-name"`（2026-09-26：为 C23 十进制字面量后缀补的引擎能力）──
# 动机：跨声明曾是"后者整体覆盖"，插件想给核心的**命名条目列表**（如 C 的数字形态
# `[[number.based]] name = "c_dec"`）补一个字段，只能整条重抄（知识重复 + 必然漂移）。
# 语义实现见 `core/config_registry.py::merge_by_name`；默认仍是覆盖（对既有配置零影响）。


def test_merge_field_rejects_unknown_mode(tmp_path):
    """`merge` 只认 `"by-name"`——写别的值 → ConfigError（fail-fast，不静默当覆盖）。"""
    _write_tpc(tmp_path, '[lexer]\nbad = { file = "x.toml", merge = "append" }\n')
    with pytest.raises(ConfigError, match="merge 只支持"):
        _load_meta_declarations(grammar_dir=str(tmp_path))


def _run_decls(root, pairs):
    """按 (name, file, section, merge) 造声明元组并解析（绕开 declare 的去重）。"""
    decls = [
        (name, fname, section, "temp", True, "", None, merge)
        for name, fname, section, merge in pairs
    ]
    return ConfigRegistry._resolve_decls(
        decls, str(root), None, "", {"temp": str(root)}
    )[0]


def test_merge_by_name_patches_and_appends(isolated_registry):
    """按名合并：同名条目**深合并**（保序）、新名条目**追加**、dict 其他键递归合并。"""
    root = isolated_registry
    (root / "core.toml").write_text(
        '[num]\nbased = [{ name = "a", v = 1 }, { name = "b", v = 2 }]\nother = 1\n',
        encoding="utf-8",
    )
    (root / "ext.toml").write_text(
        '[num]\nbased = [{ name = "a", w = 9 }, { name = "c" }]\n',
        encoding="utf-8",
    )
    loaded = _run_decls(
        root,
        [("t.num", "core.toml", "num", None), ("t.num", "ext.toml", "num", "by-name")],
    )
    assert loaded["t.num"]["based"] == [
        {"name": "a", "v": 1, "w": 9},
        {"name": "b", "v": 2},
        {"name": "c"},
    ]
    assert loaded["t.num"]["other"] == 1


def test_same_name_without_merge_still_overrides(isolated_registry):
    """缺省语义**不变**：同名声明仍是"后者覆盖"（不搞隐式魔法）。"""
    root = isolated_registry
    (root / "core.toml").write_text('[num]\nbased = [{ name = "a" }]\n', encoding="utf-8")
    (root / "ext.toml").write_text('[num]\nbased = [{ name = "b" }]\n', encoding="utf-8")
    loaded = _run_decls(
        root,
        [("t.num", "core.toml", "num", None), ("t.num", "ext.toml", "num", None)],
    )
    assert loaded["t.num"]["based"] == [{"name": "b"}]


def test_merge_by_name_rejects_unnamed_entries(isolated_registry):
    """按名合并的前提是"认得出同一条目"：无名条目 → fail-fast（不猜、不静默追加）。"""
    root = isolated_registry
    (root / "core.toml").write_text('[num]\nbased = [{ name = "a" }]\n', encoding="utf-8")
    (root / "ext.toml").write_text('[num]\nbased = [{ v = 1 }]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="by-name"):
        _run_decls(
            root,
            [("t.num", "core.toml", "num", None),
             ("t.num", "ext.toml", "num", "by-name")],
        )


def test_merge_by_name_requires_list_of_named_dicts(isolated_registry):
    """列表元素不是表 / 名字为空串 → 同样 fail-fast。"""
    root = isolated_registry
    (root / "core.toml").write_text('[num]\nbased = [{ name = "a" }]\n', encoding="utf-8")
    (root / "ext.toml").write_text('[num]\nbased = [1]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="by-name"):
        _run_decls(
            root,
            [("t.num", "core.toml", "num", None),
             ("t.num", "ext.toml", "num", "by-name")],
        )


# ── 用户 tpc_config.json 的损坏处置（$TPC_CONFIG 注入临时配置） ──


def _write_user_config(tmp_path, content: str, monkeypatch):
    cfg = tmp_path / "tpc_config.json"
    cfg.write_text(content, encoding="utf-8")
    monkeypatch.setenv("TPC_CONFIG", str(cfg))
    return cfg


def test_user_config_valid_pipeline_section_read(tmp_path, monkeypatch):
    """合法用户配置：pipeline 段被读成默认参数。"""
    from pipeline import _load_pipeline_defaults

    _write_user_config(tmp_path, '{"pipeline": {"lang": "verilog"}}', monkeypatch)
    assert _load_pipeline_defaults() == {"lang": "verilog"}


def test_user_config_malformed_pipeline_fails_fast(tmp_path, monkeypatch):
    """用户配置损坏 → ConfigError（不静默丢默认值；"假绿"防护）。"""
    from pipeline import _load_pipeline_defaults

    _write_user_config(tmp_path, "{ not json", monkeypatch)
    with pytest.raises(ConfigError, match="读取/解析失败"):
        _load_pipeline_defaults()


def test_user_config_pipeline_section_wrong_type_fails_fast(tmp_path, monkeypatch):
    """pipeline 段非对象 → ConfigError（不给静默回退）。"""
    from pipeline import _load_pipeline_defaults

    _write_user_config(tmp_path, '{"pipeline": [1, 2]}', monkeypatch)
    with pytest.raises(ConfigError, match="pipeline 段应为对象"):
        _load_pipeline_defaults()


def test_user_config_malformed_grammar_lookup_fails_fast(tmp_path, monkeypatch):
    """grammar 包里解析用户配置同样 fail-fast（不静默回退默认语言包）。"""
    from core.config_registry import _find_grammar_tpc_toml

    _write_user_config(tmp_path, "{ not json", monkeypatch)
    with pytest.raises(ConfigError, match="读取/解析失败"):
        _find_grammar_tpc_toml()


def test_user_config_grammar_wrong_type_fails_fast(tmp_path, monkeypatch):
    """grammar 段类型非法（非字符串/对象）→ ConfigError。"""
    from core.config_registry import _find_grammar_tpc_toml

    _write_user_config(tmp_path, '{"grammar": [1]}', monkeypatch)
    with pytest.raises(ConfigError, match="grammar 段应为字符串或对象"):
        _find_grammar_tpc_toml()


# ── 模块级 declare_cfg 的语言作用域：切语言时未声明的键**推回编译期默认** ─────────
# 2026-09-26 修：此前 `_push_loaded_config` 在 `KeyError`（本包未声明）时"什么都不推"，
# 于是模块变量留着**上一个语言**推的值 ⇒ 跨语言串味。实测症状：先扫 verilog 再切 C，
# C 源（无 `rules/`，也不声明 `linter.style_check`）上跑起 verilog 的排版检查，
# 长行报 `ST003`（`TODO.md`「跨语言检查规则泄漏」）。


def test_switching_language_resets_undeclared_config_keys():
    """verilog 声明 `linter.style_check`、C 不声明 ⇒ 切到 C 后必须回到默认（`{}`）。

    判据 = **同一份源在"先跑过别的语言"与"干净进程"下配置值相同**——这正是跨语言
    串味的可证伪判据（旧实现下第二步仍是 verilog 的值）。
    """
    from linter import scanner as sc

    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    def _load(rel: str) -> None:
        pack = os.path.join(root, rel)
        ConfigRegistry.load_language(rel, plugins_dir=os.path.join(pack, "plugins"))

    _load(os.path.join("grammar", "verilog"))
    assert sc._style_check_cfg.get("enabled") is True, sc._style_check_cfg

    _load(os.path.join("grammar", "c"))
    assert sc._style_check_cfg == {}, sc._style_check_cfg
    assert sc._macro_hygiene_cfg == {}, sc._macro_hygiene_cfg


def test_declare_cfg_defaults_must_agree():
    """同一 key 的多处 `declare_cfg` 默认值不一致 → fail-fast。

    切语言要"推回默认"，故默认值必须唯一——两处不同时推哪个都错，只能报错。
    """
    from core import config_registry as cr

    key = "t.mismatch_defaults"
    cr.declare_cfg(key, {"a": 1}, "tests.fake_a", "_v_a")
    with pytest.raises(ConfigError, match="编译期默认值不一致"):
        cr.declare_cfg(key, {"a": 2}, "tests.fake_b", "_v_b")
