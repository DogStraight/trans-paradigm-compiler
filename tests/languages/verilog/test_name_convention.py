"""tests/languages/verilog/test_name_convention.py — name_check 插件（命名约定检查）。

L1 声明式规则表（[[checks]]，规则=数据）的端到端验证：引擎通用执行器
（analyzer/checks.py）在 analyzer 遍历后按符号 kind 分发 rules/naming.toml
的 pattern 判定，报 NC001-NC010 诊断。

验证面：
    - 命名合规（小写下划线 module/port/wire）→ 零诊断
    - 命名违规（大写/驼峰）→ 对应 NC 码 warning
    - kind 分发正确性（module 违规不误报 port 规则）
    - 大写下划线族（parameter/localparam/genvar）独立判定
    - 规则表加载 fail-fast（id 重复 / severity 非法 / pattern 非法正则）
    - 无规则表语言（c4，无 rules/ 目录）零诊断（执行器零开销返回）
    - L2 handler 兜底（临时插件目录：加载/命中/通过/fail-fast）
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from core.define import DEFAULT_RULES_DIR, GrammarRulesRegister  # noqa: E402
from parser import setup_grammar  # noqa: E402
from parser.parser_core import Parser  # noqa: E402
from parser.rule_selector import RuleSelector  # noqa: E402
from lexer import Lexer  # noqa: E402
from analyzer.traversal import AnalysisTraversal  # noqa: E402
from core.check_registry import load_check_rules, get_check_rules, get_rules_for_kind  # noqa: E402


@pytest.fixture(scope="module")
def ctx(config_loaded):
    rules = setup_grammar(DEFAULT_RULES_DIR, GrammarRulesRegister.get_default())
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(
        rules_dir=DEFAULT_RULES_DIR,
        rules=rules,
        rule_selector=rs,
        log_file="",
    )
    lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
    return rules, parser, lexer


def _diags(ctx, src):
    """解析 + 语义分析，返回 [(code, level, message)]。"""
    rules, parser, lexer = ctx
    tokens = lexer.tokenize(src)
    ast = parser.parse(tokens)
    assert not parser._parse_truncated, "完整解析应无 truncated"
    at = AnalysisTraversal(rules)
    at.analyze(ast)
    return [(d.code, d.level, d.message) for d in at.diagnostics]


class TestNamingRuleTable:
    """规则表加载 + 校验（fail-fast）。"""

    def test_rules_loaded(self, config_loaded):
        rules = get_check_rules()
        ids = {r["id"] for r in rules}
        assert {"NC001", "NC005", "NC006"} <= ids  # module/port/parameter 族在
        assert len(rules) >= 10

    def test_kind_dispatch(self, config_loaded):
        module_rules = get_rules_for_kind("module")
        assert any(r["id"] == "NC001" for r in module_rules)
        param_rules = get_rules_for_kind("parameter")
        assert any(r["id"] == "NC006" for r in param_rules)
        # kind 分发互斥：module 规则不落入 port 分发
        assert not any(r["id"] == "NC001" for r in get_rules_for_kind("port"))

    def test_id_unique(self, config_loaded):
        rules = get_check_rules()
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids)), "规则 id 必须全局唯一"

    def test_invalid_severity_failfast(self, tmp_path, config_loaded):
        """severity 非法 → fail-fast 报错（ADR-0003）。"""
        from core.check_registry import _CHECK_RULES, load_check_rules
        from core.errors import ConfigError

        # 临时插件目录：构造非法规则文件
        plug = tmp_path / "badplug"
        (plug / "rules").mkdir(parents=True)
        (plug / "rules" / "bad.toml").write_text(
            '[[checks]]\nid = "X001"\nkind = "module"\nseverity = "fatal"\n'
            'message = "x"\npattern = "^a$"\n',
            encoding="utf-8",
        )
        # 用独立缓存键隔离：直接调 discover+validate 路径（load 会缓存，
        # 用 tmp 目录做键——但 _resolve_plugins_dir 只认默认/绝对路径）
        # 简化：直接构造验证路径——手动调用 _validate_rule
        from core.check_registry import _validate_rule

        with pytest.raises(ConfigError):
            _validate_rule({"id": "X1", "kind": "module", "severity": "fatal", "message": "x"}, "f.toml", set())

    def test_invalid_pattern_failfast(self, config_loaded):
        """pattern 非法正则 → fail-fast。"""
        from core.check_registry import _validate_rule
        from core.errors import ConfigError

        with pytest.raises(ConfigError):
            _validate_rule(
                {"id": "X2", "kind": "module", "severity": "warning",
                 "message": "x", "pattern": "("},
                "f.toml", set(),
            )

    def test_missing_kind_failfast(self, config_loaded):
        """缺 kind（分发键）→ fail-fast。"""
        from core.check_registry import _validate_rule
        from core.errors import ConfigError

        with pytest.raises(ConfigError):
            _validate_rule(
                {"id": "X3", "severity": "warning", "message": "x", "pattern": "^a$"},
                "f.toml", set(),
            )


class TestNamingCheck:
    """名称检查端到端（NC 码诊断）。"""

    def test_clean_names_no_diag(self, ctx):
        """全小写下划线 → 零诊断。"""
        src = """module mux_2x1 (
  input  wire a_in,
  input  wire b_in,
  output wire y_out
);
  assign y_out = a_in | b_in;
endmodule
"""
        assert _diags(ctx, src) == []

    def test_module_uppercase_nc001(self, ctx):
        """module 名大写 → NC001。"""
        src = "module Mux2x1;\nendmodule\n"
        diags = _diags(ctx, src)
        assert ("NC001", "warning") in {(c, l) for c, l, _ in diags}
        assert any("Mux2x1" in m for _, _, m in diags)

    def test_port_uppercase_nc005(self, ctx):
        """端口名大写 → NC005（module 合规不误报）。"""
        src = """module mux_2x1 (
  input  wire A_IN,
  output wire Y_OUT
);
  assign Y_OUT = A_IN;
endmodule
"""
        diags = _diags(ctx, src)
        codes = {c for c, _, _ in diags}
        assert "NC005" in codes  # 端口违规
        assert "NC001" not in codes  # module mux_2x1 合规
        assert "NC003" not in codes  # wire 类型名不查（wire 是类型非符号）

    def test_non_ansi_port_no_dup(self, ctx):
        """非 ANSI 端口（方向声明 + 类型声明分离）不报重复声明 E001。"""
        src = """module m;
  output Q;
  reg Q;
endmodule
"""
        diags = _diags(ctx, src)
        codes = {c for c, _, _ in diags}
        assert "E001" not in codes  # 方向声明 + 类型声明 = 同一信号，非重复

    def test_non_ansi_port_reg_naming(self, ctx):
        """非 ANSI 端口类型声明（reg）走 NC004 命名检查。"""
        src = """module m;
  output Q_BAD;
  reg Q_BAD;
endmodule
"""
        diags = _diags(ctx, src)
        codes = {c for c, _, _ in diags}
        assert "NC004" in codes  # reg 类型声明命名违规
        assert "E001" not in codes

    def test_parameter_uppercase_nc006(self, ctx):
        """参数名小写 → NC006（参数族大写下划线）。"""
        src = """module m #(
  parameter width = 8
)();
endmodule
"""
        diags = _diags(ctx, src)
        assert ("NC006", "warning") in {(c, l) for c, l, _ in diags}

    def test_parameter_clean(self, ctx):
        """参数名大写 → 零诊断。"""
        src = """module m #(
  parameter WIDTH = 8
)();
endmodule
"""
        assert _diags(ctx, src) == []

    def test_wire_lowercase_ok(self, ctx):
        """wire 小写合规；大写违规 NC003。"""
        src = "module m;\n  wire DATA_BUS;\nendmodule\n"
        diags = _diags(ctx, src)
        assert ("NC003", "warning") in {(c, l) for c, l, _ in diags}

    def test_genvar_uppercase_ok(self, ctx):
        """genvar 大写合规（大写下划线族）。"""
        src = (
            "module m;\n"
            "  genvar I;\n"
            "  generate for (I = 0; I < 4; I = I + 1) begin: g\n"
            "  end\n"
            "  endgenerate\n"
            "endmodule\n"
        )
        assert _diags(ctx, src) == []

    def test_instance_lowercase_ok(self, ctx):
        """实例名小写合规；大写违规 NC002。"""
        src = (
            "module m;\n"
            "  adder U_ADD ();\n"
            "endmodule\n"
            "module adder;\n"
            "endmodule\n"
        )
        diags = _diags(ctx, src)
        # adder（module）与 U_ADD（instance）——U_ADD 违规 NC002
        codes = {c for c, _, _ in diags}
        assert "NC002" in codes
        assert "NC001" not in codes  # adder 合规

    def test_function_task_naming(self, ctx):
        """函数/任务名大写 → NC009/NC010。"""
        src = """module m;
  function MyFunc;
    input x;
    MyFunc = x;
  endfunction
  task MyTask;
  endtask
endmodule
"""
        diags = _diags(ctx, src)
        codes = {c for c, _, _ in diags}
        assert "NC009" in codes
        assert "NC010" in codes


class TestNoRulesLanguage:
    """无规则表语言（c4，无 rules/ 目录）→ 执行器零开销返回，零诊断。"""

    def test_c4_zero_diag(self):
        """c4 源码经 analyzer 无 NC 诊断（规则表空）。"""
        from core.define import GrammarRulesRegister
        from parser import setup_grammar
        from parser.parser_core import Parser
        from parser.rule_selector import RuleSelector
        from lexer import Lexer

        rules = setup_grammar(
            "grammar/c4", GrammarRulesRegister()
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rs = RuleSelector(rules, stmt_names)
        parser = Parser(rules_dir="grammar/c4", rules=rules, rule_selector=rs)
        lexer = Lexer(rules_dir="grammar/c4")
        src = "int main() { int a; a = 1; return a; }"
        tokens = lexer.tokenize(src)
        ast = parser.parse(tokens)
        at = AnalysisTraversal(rules, rules_dir="grammar/c4")
        at.analyze(ast)
        assert at.diagnostics == []


class TestUserCheckConfig:
    """P4 用户配置层：config/tpc_config.json 的 checks 段（enabled/overrides/per_file）。

    经 $TPC_CONFIG 注入临时配置文件（find_user_config 优先级链第一档），
    _USER_CONFIG_CACHE 每个测试前清理（缓存按配置路径键控）。
    """

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from core import check_registry

        check_registry._USER_CONFIG_CACHE.clear()
        yield
        check_registry._USER_CONFIG_CACHE.clear()

    def _run_cfg(self, ctx, src, checks: dict, monkeypatch, tmp_path):
        """$TPC_CONFIG → 临时 config.json（checks 段）→ 分析。"""
        import json

        cfg = tmp_path / "tpc_config.json"
        cfg.write_text(json.dumps({"checks": checks}), encoding="utf-8")
        monkeypatch.setenv("TPC_CONFIG", str(cfg))
        rules, parser, lexer = ctx
        tokens = lexer.tokenize(src)
        ast = parser.parse(tokens)
        assert not parser._parse_truncated
        at = AnalysisTraversal(rules)
        at.analyze(ast)
        return [(d.code, d.level, d.message) for d in at.diagnostics]

    def test_enabled_filters(self, ctx, monkeypatch, tmp_path):
        """enabled 只启用列出的规则（不选即关）。"""
        src = (
            "module Mux2x1 (\n"
            "  input wire A_IN,\n"
            "  output wire Y_OUT\n"
            ");\n"
            "  assign Y_OUT = A_IN;\n"
            "endmodule\n"
        )
        # 只启用 NC001（module 命名）——NC005（端口）被关闭
        diags = self._run_cfg(ctx, src, {"enabled": ["NC001"]}, monkeypatch, tmp_path)
        codes = {c for c, _, _ in diags}
        assert "NC001" in codes
        assert "NC005" not in codes

    def test_enabled_empty_disables_all(self, ctx, monkeypatch, tmp_path):
        """enabled = [] → 全部规则关闭（"不选即关"）。"""
        src = "module Mux2x1;\nendmodule\n"
        diags = self._run_cfg(ctx, src, {"enabled": []}, monkeypatch, tmp_path)
        assert diags == []

    def test_override_severity(self, ctx, monkeypatch, tmp_path):
        """overrides 提升 severity：NC001 warning → error。"""
        src = "module Mux2x1;\nendmodule\n"
        diags = self._run_cfg(
            ctx,
            src,
            {"overrides": {"NC001": {"severity": "error"}}},
            monkeypatch,
            tmp_path,
        )
        assert ("NC001", "error") in {(c, l) for c, l, _ in diags}

    def test_override_downgrade(self, ctx, monkeypatch, tmp_path):
        """overrides 降级：NC001 → info。"""
        src = "module Mux2x1;\nendmodule\n"
        diags = self._run_cfg(
            ctx,
            src,
            {"overrides": {"NC001": {"severity": "info"}}},
            monkeypatch,
            tmp_path,
        )
        assert ("NC001", "info") in {(c, l) for c, l, _ in diags}

    def test_per_file_disabled(self, ctx, monkeypatch, tmp_path):
        """per_file glob 豁免：符号文件匹配 → disabled 规则跳过。"""
        import json

        src = "module Mux2x1;\nendmodule\n"
        tb_dir = tmp_path / "tb"
        tb_dir.mkdir()
        fpath = tb_dir / "tb_top.sv"
        fpath.write_text(src, encoding="utf-8")
        # 用户配置：per_file 豁免 tb/*.sv 的 NC001
        cfg = tmp_path / "tpc_config.json"
        cfg.write_text(
            json.dumps(
                {"checks": {"per_file": {"tb/*.sv": {"disabled": ["NC001"]}}}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("TPC_CONFIG", str(cfg))
        from analyzer.checker import ProjectChecker

        checker = ProjectChecker(rules_dir="grammar/verilog")
        report = checker.check(str(fpath))
        sem = [d for f in report["files"] for d in f["semantic"]]
        assert not any(d["code"] == "NC001" for d in sem), "tb/*.sv 应豁免 NC001"

    def test_per_file_not_matched(self, ctx, monkeypatch, tmp_path):
        """per_file glob 不匹配 → 不豁免（NC001 仍报）。"""
        import json

        src = "module Mux2x1;\nendmodule\n"
        rtl_dir = tmp_path / "rtl"
        rtl_dir.mkdir()
        fpath = rtl_dir / "rtl_top.sv"
        fpath.write_text(src, encoding="utf-8")
        cfg = tmp_path / "tpc_config.json"
        cfg.write_text(
            json.dumps(
                {"checks": {"per_file": {"tb/*.sv": {"disabled": ["NC001"]}}}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("TPC_CONFIG", str(cfg))
        from analyzer.checker import ProjectChecker

        checker = ProjectChecker(rules_dir="grammar/verilog")
        report = checker.check(str(fpath))
        sem = [d for f in report["files"] for d in f["semantic"]]
        assert any(d["code"] == "NC001" for d in sem), "rtl/top.sv 不应豁免"

    def test_invalid_enabled_ref_failfast(self, ctx, monkeypatch, tmp_path):
        """enabled 引用不存在的规则 id → fail-fast。"""
        import json

        from core.errors import ConfigError

        cfg = tmp_path / "tpc_config.json"
        cfg.write_text(
            json.dumps({"checks": {"enabled": ["NOPE"]}}), encoding="utf-8"
        )
        monkeypatch.setenv("TPC_CONFIG", str(cfg))
        with pytest.raises(ConfigError):
            self._run_cfg(
                ctx, "module m;\nendmodule\n", {"enabled": ["NOPE"]},
                monkeypatch, tmp_path,
            )

    def test_invalid_override_severity_failfast(self, ctx, monkeypatch, tmp_path):
        """overrides severity 非法 → fail-fast。"""
        from core.errors import ConfigError

        with pytest.raises(ConfigError):
            self._run_cfg(
                ctx, "module m;\nendmodule\n",
                {"overrides": {"NC001": {"severity": "fatal"}}},
                monkeypatch, tmp_path,
            )


class TestHandlerFallback:
    """L2 脚本 handler 兜底（规则带 handler 字段，pattern 判定不足时）。

    handler 签名 fn(symbol, rule, context) -> str | None（None = 通过，
    str = 诊断消息，引擎统一插值 + 报告）。临时插件目录验证加载/调用/
    fail-fast，不污染正式插件。
    """

    @pytest.fixture
    def tmp_plugin(self, tmp_path):
        """临时插件目录（遵循真实约定：rules_dir/plugins/<name>/rules/）。"""
        plug = tmp_path / "plugins" / "hplug"
        (plug / "rules").mkdir(parents=True)
        (plug / "rules" / "h.toml").write_text(
            '[[checks]]\n'
            'id = "H001"\n'
            'category = "naming"\n'
            'severity = "warning"\n'
            'kind = "module"\n'
            'message = "module {name} 禁止以 _t 结尾（{id}）"\n'
            'handler = "_h.py:check_no_t_suffix"\n',
            encoding="utf-8",
        )
        (plug / "rules" / "_h.py").write_text(
            "def check_no_t_suffix(symbol, rule, context):\n"
            "    name = symbol.name\n"
            "    return None if not name.endswith('_t') else 'module {name} 禁止以 _t 结尾'\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run_with_plugin(self, ctx, src, rules_dir):
        """用指定规则目录（其 plugins/ 承载规则表）跑语义分析。"""
        from core.check_registry import load_check_rules

        load_check_rules(os.path.join(str(rules_dir), "plugins"))
        rules, parser, lexer = ctx
        tokens = lexer.tokenize(src)
        ast = parser.parse(tokens)
        assert not parser._parse_truncated
        at = AnalysisTraversal(rules, rules_dir=str(rules_dir))
        at.analyze(ast)
        return [(d.code, d.level, d.message) for d in at.diagnostics]

    def test_handler_hit(self, ctx, tmp_plugin):
        """handler 返回消息 → 报诊断（handler 自管消息文本，引擎插值）。"""
        diags = self._run_with_plugin(
            ctx, "module foo_t;\nendmodule\n", tmp_plugin
        )
        assert ("H001", "warning") in {(c, l) for c, l, _ in diags}
        assert any("foo_t" in m and "禁止以 _t 结尾" in m for _, _, m in diags)

    def test_handler_pass(self, ctx, tmp_plugin):
        """handler 返回 None → 通过（零诊断）。"""
        diags = self._run_with_plugin(
            ctx, "module foo;\nendmodule\n", tmp_plugin
        )
        assert not [d for d in diags if d[0] == "H001"]

    def test_handler_missing_module_failfast(self, ctx, tmp_path):
        """handler 模块缺失 → fail-fast（ADR-0003）。"""
        plug = tmp_path / "plugins" / "bplug"
        (plug / "rules").mkdir(parents=True)
        (plug / "rules" / "b.toml").write_text(
            '[[checks]]\nid = "B001"\nkind = "module"\n'
            'message = "x"\nhandler = "_missing.py:fn"\n',
            encoding="utf-8",
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            self._run_with_plugin(ctx, "module a;\nendmodule\n", tmp_path)


class TestCommentDrivenCases:
    """注释驱动测试（Semgrep 式零代码测试）：插件 cases/ 目录样例全过。

    样例源文件内嵌 `// ruleid: X`（必须命中）/ `// ok: X`（不得命中）
    注释，框架（analyzer/check_test.py）运行 ProjectChecker 后断言命中
    集合。新增样例 = 新增断言（零代码），规则行为变化时随样例自动更新
    语义。cases/ 目录：grammar/verilog/plugins/checks/name_check/cases/*.sv。
    """

    def test_name_check_cases(self, config_loaded, tmp_path):
        import glob
        import shutil

        from analyzer.check_test import run_comment_driven
        from analyzer.checker import ProjectChecker

        # cases/ 随组件所在位置（聚类目录支持）：从插件根递归定位
        plugins_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))),
            "grammar", "verilog", "plugins",
        )
        matches = glob.glob(
            os.path.join(plugins_dir, "**", "name_check", "cases", "*.sv"),
            recursive=True,
        )
        assert matches, f"cases 目录无样例: {plugins_dir}/**/name_check/cases"
        samples = sorted(matches)

        checker = ProjectChecker(rules_dir="grammar/verilog")
        all_failures = []
        for sample in samples:
            # check 需要独立文件（ProjectChecker 按路径解析；保留原文件名
            # ——NC011 模块名-文件名一致性按样例文件基名判定）
            dst = tmp_path / os.path.basename(sample)
            shutil.copy(sample, dst)
            fails = run_comment_driven(checker, str(dst))
            if fails:
                all_failures.append(f"--- {os.path.basename(sample)} ---")
                all_failures.extend(fails)
        assert not all_failures, "\n".join(all_failures)
