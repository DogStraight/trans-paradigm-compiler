"""generate.py — fuzz 输入生成：语法驱动 + 变异（零第三方依赖）。

语法驱动：复用与 linter 同源的 production 编译路径
（parser.rule_selector.analyze_production_features → build_slice_tree），
随机展开 feature dict（token/call/choice/seq/optional/repeat/plus）生成输入。
变异：从语料 token 化后做增/删/改/换/截断。

配置即数据的好处：fuzzer 直接从 grammar TOML 驱动，无需手写生成器语法。

Doc: tests/fuzz/README.md（fuzz 验证说明）
"""

from __future__ import annotations

import os
import random
from typing import cast

from core.define import GrammarRulesRegister, Token
from core.token_protocol import TRIVIA_TOKEN_TYPES
from lexer import Lexer
from linter.grammar_slicer import build_slice_tree
from lexer.lexer_utils import get_token_define_merged
from parser import setup_grammar

# 入口规则候选（按优先级尝试；缺失则回退第一个 is_block 规则）
ROOT_CANDIDATES = ["Root", "SourceText", "ModuleDecl"]
MAX_DEPTH = 8
_ID_POOL = ["a", "b", "c", "clk", "data", "sig", "m", "x", "y", "state", "tmp",
            "DATA_W", "W", "N", "foo", "bar", "m0", "u1", "out_bus"]
_IDS = "abcdefghijklmnopqrstuvwxyz"


def build_token_map(rules_dir: str) -> dict[str, str]:
    """token_type → 字面量映射（id/number/string/newline 走合成分支）。"""
    td = get_token_define_merged(rules_dir) or {}
    m: dict[str, str] = {}
    for key, lit in (td.get("id", {}).get("keyword", {}) or {}).items():
        m[f"keyword.{key}"] = lit
    for sec in ("symbol.base", "symbol.extend"):
        for key, lit in (td.get(sec) or {}).items():
            m[f"{sec}.{key}"] = lit
    for open_, close, name in (td.get("bracket", {}).get("pairs", []) or []):
        m[f"bracket.l_{name}"] = open_
        m[f"bracket.r_{name}"] = close
    return m


class GrammarFuzzer:
    """从 grammar 规则表随机生成（近似合法的）输入。"""

    def __init__(self, rules_dir: str, rng: random.Random):
        register = GrammarRulesRegister.get_default()
        self._rules = setup_grammar(rules_dir, register)
        self._tree = build_slice_tree(self._rules)
        self._tok = build_token_map(rules_dir)
        self._rng = rng
        self._entry = self._pick_entry()

    def _pick_entry(self) -> str:
        for name in ROOT_CANDIDATES:
            if name in self._tree:
                return name
        for name, info in self._tree.items():
            if info.get("is_block"):
                return name
        return next(iter(self._tree))

    # ── 生成 ────────────────────────────────

    def generate(self, newline_every: int = 12) -> str:
        """生成一个程序：token 空格连接，每 N 个 token 插一个换行。"""
        toks = self.gen_rule(self._entry, 0)
        words = [w for w in toks.split(" ") if w]
        out: list[str] = []
        for i, w in enumerate(words):
            if i and i % newline_every == 0:
                out.append("\n")
            out.append(w)
        return " ".join(out)

    def gen_rule(self, name: str, depth: int) -> str:
        if depth > MAX_DEPTH:
            return self._gen_id()
        info = self._tree.get(name)
        if not info or not info.get("prods"):
            return ""
        return " ".join(
            p for p in (self.gen_feature(f, depth) for f in info["prods"]) if p
        )

    def gen_feature(self, feat: dict, depth: int) -> str:
        t = feat.get("type")
        if t == "token":
            return self._gen_token(feat.get("token_type", ""))
        if t == "call":
            return self.gen_rule(feat.get("name", ""), depth + 1)
        if t == "choice":
            return self.gen_feature(self._rng.choice(feat["alternatives"]), depth)
        if t == "seq":
            return " ".join(
                p for p in (self.gen_feature(x, depth) for x in feat["items"]) if p
            )
        if t == "optional":
            return self.gen_feature(feat["elem"], depth) if self._rng.random() < 0.5 else ""
        if t in ("repeat", "plus"):
            lo = 0 if t == "repeat" else 1
            n = self._rng.randint(lo, 3)
            return " ".join(
                p for p in (self.gen_feature(feat["elem"], depth) for _ in range(n)) if p
            )
        return ""

    def _gen_token(self, token_type: str) -> str:
        if token_type == "id":
            return self._gen_id()
        if token_type == "literal.number":
            return str(self._rng.randint(0, 65535))
        if token_type == "literal.string":
            return f'"s{self._rng.randint(0, 99)}"'
        if token_type == "newline":
            return "\n"
        return self._tok.get(token_type, "?")

    def _gen_id(self) -> str:
        return self._rng.choice(_ID_POOL) + str(self._rng.randint(0, 9))


# ── 变异 fuzzing ────────────────────────────

_OPS = ["delete", "duplicate", "replace", "insert", "swap", "truncate"]


def _content_pool(token_map: dict[str, str]) -> list[str]:
    pool = list(token_map.values())
    pool += ["if", "else", "begin", "end", "module", "always", "wire", "reg",
             "input", "output", "assign", "case", "for", "parameter"]
    pool += _ID_POOL
    return pool


def mutate_source(src: str, rng: random.Random, token_map: dict[str, str],
                  rules_dir: str) -> str:
    """token 级变异：增/删/改/换/截断 1-3 处。"""
    lexer = Lexer(rules_dir=rules_dir)
    try:
        toks = lexer.tokenize(src)
    except Exception:
        return src
    idx = [i for i, t in enumerate(toks) if t.type not in TRIVIA_TOKEN_TYPES]
    if not idx:
        return src
    for _ in range(rng.randint(1, 3)):
        op = rng.choice(_OPS)
        if not idx:
            break
        pos = rng.choice(idx)
        if op == "delete":
            toks.pop(pos)
        elif op == "duplicate":
            toks.insert(pos, toks[pos])
        elif op == "replace":
            toks[pos].content = rng.choice(_content_pool(token_map))
        elif op == "insert":
            toks.insert(pos, cast(Token, rng.choice([_mk_tok(t) for t in
                                                     [";", "begin", "end", "=", "module", "if",
                                                      "always", ")", "(", "1", "clk"]])))
        elif op == "swap":
            j = rng.choice(idx)
            toks[pos], toks[j] = toks[j], toks[pos]
        elif op == "truncate":
            toks = toks[:pos]
            break
        idx = [i for i, t in enumerate(toks) if t.type not in TRIVIA_TOKEN_TYPES]
    return " ".join(t.content for t in toks)


class _FakeTok:
    def __init__(self, content: str):
        self.content = content
        self.type = "id"


def _mk_tok(content: str) -> _FakeTok:
    return _FakeTok(content)


# ── 种子收集 ────────────────────────────────

def collect_seeds(*roots: str) -> list[str]:
    files: list[str] = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _, names in os.walk(root):
            for n in sorted(names):
                if n.endswith(".v"):
                    files.append(os.path.join(dirpath, n))
    return files
