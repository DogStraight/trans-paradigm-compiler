"""原型验证：宏体形态分类检测（完整语法单元 vs 残缺片段）。

思路：宏体放进几种最小语法上下文包裹，能完整解析 → 完整单元（卫生，
将来可保留为 AST 节点）；所有包裹都失败 → 残缺片段（不卫生，只能原位
展开）。这是「不卫生宏体检测」的可行性验证。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from core.plugin_loader import load_all_components
from parser import Parser, setup_grammar
from parser.rule_selector import RuleSelector
from lexer import Lexer, pre_scan, load_pre_scan_config
from parser.parser_core import ParseError

RULES = "grammar/verilog"
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _build_shared():
    rules_dir = os.path.join(_ROOT, RULES)
    plugins_dir = os.path.join(rules_dir, "plugins")
    ConfigRegistry.load_all(rules_dir, ext_dirs=None, plugins_dir=plugins_dir)
    load_all_components()
    register = GrammarRulesRegister.get_default()
    rules = setup_grammar(rules_dir, register, ext_dirs=None)
    stmt_names = [n for n, r in rules.items()
                  if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()]
    return {
        "rules": rules,
        "rule_selector": RuleSelector(rules, stmt_names),
        "lexer": Lexer(rules_dir=rules_dir),
    }

SHARED = _build_shared()

def _try_parse(text: str) -> tuple[bool, str]:
    try:
        cfg = load_pre_scan_config(os.path.join(_ROOT, RULES))
        pre = pre_scan(text, cfg)
        parser = Parser(rules_dir=os.path.join(_ROOT, RULES),
                        pre_symbols=pre, rules=SHARED["rules"],
                        rule_selector=SHARED["rule_selector"])
        parser.pre_hints = cfg.get("hints", {})
        tokens = SHARED["lexer"].tokenize(text)
        ast = parser.parse(tokens)
        if ast is None or getattr(parser, "_parse_truncated", False):
            return False, "truncated"
        return True, "ok"
    except ParseError:
        return False, "parse-error"
    except Exception as e:  # noqa: BLE001
        return False, f"exc:{type(e).__name__}"

WRAPS = {
    "stmt":   "module m;\ninitial begin\n{b}\nend\nendmodule",
    "decl":   "module m;\n{b}\nendmodule",
    "expr":   "module m;\nreg x;\ninitial begin\nx = {b};\nend\nendmodule",
    "port":   "module m;\ninput x {b};\nendmodule",
}

SAMPLES = {
    "= 1'b1":              "ice40 端口默认值宏",
    "[3:0]":               "范围片段",
    "+ 4":                 "运算符续段",
    "begin":               "块开头（缺 end）",
    "end":                 "块结尾（缺 begin）",
    ", .q(q)":             "端口连接续段",
    "else y = 2;":         "else 分支（缺 if 头）",
    "initial Q = 0;":      "SB_DFF_INIT 语句体宏（完整语句）",
    "reg [3:0] q;":        "完整声明",
    "assign y = 1'b1;":    "完整连续赋值",
    "if (x) y = 1; else y = 2;": "完整 if 语句",
    "y = 1'b1;":           "完整过程赋值",
    "empty_statement":     "picorv32 assert 宏体",
    "1'b1":                "完整表达式",
}

# 续接 token：以这些开头的宏体是"残缺续段"（依赖前置上下文）——
# 首 token 预过滤，防止包裹模板的宽松接受（如 `+ 4` 被当一元正号、
# `input x = 1'b1` 被当合法端口默认值）。
_CONT_LEAD = ("=", "[", "(", ",", ".", "+", "-", "*", "/", "&", "|",
              "^", "~", "!", "?", ":", "&&", "||", "==", "!=", "<", ">")

def _classify(body: str) -> tuple[str, str]:
    """返回 (判定, 依据)。判定 ∈ 完整语句/完整声明/完整表达式/残缺片段。"""
    lead = body.lstrip()
    if lead.startswith(_CONT_LEAD):
        return "残缺片段", f"首 token 续接（{lead.split()[0][:12]}）"
    results = {}
    for name, tpl in WRAPS.items():
        ok, _ = _try_parse(tpl.format(b=body))
        results[name] = ok
    if results["stmt"]:
        return "完整语句", "initial begin 包裹解析成功"
    if results["decl"]:
        return "完整声明", "module 体包裹解析成功"
    if results["expr"]:
        return "完整表达式", "x = 包裹解析成功"
    return "残缺片段", "全部包裹失败"

print(f"{'宏体':<34}{'stmt':<6}{'decl':<6}{'expr':<6}{'port':<6}  判定（依据）")
print("-" * 100)
for body, note in SAMPLES.items():
    results = {}
    for name, tpl in WRAPS.items():
        ok, _ = _try_parse(tpl.format(b=body))
        results[name] = "✓" if ok else "✗"
    verdict, basis = _classify(body)
    print(f"{body:<34}{results['stmt']:<6}{results['decl']:<6}"
          f"{results['expr']:<6}{results['port']:<6}  {verdict}（{basis}）({note})")
