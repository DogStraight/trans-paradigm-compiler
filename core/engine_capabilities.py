"""engine_capabilities.py — 引擎能力表（语言包 `[engine] uses` 的协商基础）。

**为什么有这张表**（0.1.3 WS2 步 3，缺口 `docs/gaps/gap-feature-scatter.md` P-C）：
原契约是 `[engine] api = "0.1"`——**整条 API 线**的 major.minor。后果：引擎 minor 一动
**所有**包都拒绝加载（哪怕该包只用语法声明、根本没碰精化协议），且报错说不出**缺哪一项**。
能力协商把"包依赖引擎"从一条粗线细化为**逐项能力 + 版本**：包只声明自己**真的用到**的
能力，引擎只对它声明过的那几项负责。

**能力 = 引擎对语言包的契约面**（不是功能开关）：包声明 `uses = ["lexer.token_ext.v1"]`
即"我按 v1 语义写词法扩展"。引擎侧某项能力语义变了 → 该项版本 +1 → **只有声明了旧版的包**
被拦下，且报错直接点名"是哪一项能力、包的版本、引擎的版本"。

**单一来源纪律**：`uses` 不许人凭记忆写——`required_capabilities()` 从语言包**自己的清单**
（tpc.toml 段 + `[capabilities]` 键 + `rules/*.toml`）机械推导，门禁
`tests/policy/test_engine_capabilities.py` 断言"推导集 ⊆ 声明集"（漏声明即红）。

Doc: core/config_lifecycle.md（包↔引擎契约节）
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from core.errors import ConfigError

# ── 能力表：能力名 → 当前版本 ────────────────────────────────
# 版本 +1 的判据：**该能力的语义/形状对语言包可见地变了**（字段增删改、加载时序变化、
# 声明面语义变化）。纯内部实现重构、性能优化、报错文案调整**不**升版本——否则
# "受影响面"会被自己放大成常态，能力协商就退化成原来的粗线。
CAPABILITIES: dict[str, str] = {
    "grammar.rules": "1",           # [grammar] files / inject（规则叠加与替换）
    "lexer.token_ext": "1",         # [lexer] token_ext / pre_scan / bracket_map
    "parser.pratt": "1",            # [parser] token_categories / operator_defs / skip_types
    "analyzer.primitives": "1",     # [analyzer] handlers / postpasses / 语义原语
    "preprocessor.pipeline": "1",   # [preprocessor] directives / macro_config / expand
    "linter.rules": "1",            # [linter] 检查器注册
    "renderer.doc_ir": "1",         # [renderer] Doc IR 渲染规则
    "render.plugins": "1",          # [render] 渲染插件
    "transform.slots": "1",         # [transform] slots / ctx_channels
    "pipeline.units": "1",          # [pipeline] units / pass / schedule
    "structure.protocol": "1",      # [structure] 单元/实例发现协议
    "checks.rules": "1",            # rules/*.toml 声明式检查规则表
    "capability.elaborator": "1",   # [capabilities] elaborator 入口
    "capability.formatter": "1",    # [capabilities] formatter 入口
    "capability.macro_policy": "1",  # [capabilities] macro_policy 入口
}

# ── 段 → 能力（推导用；`[capabilities]` 与会话/行政段单独处理） ──
SECTION_CAPABILITY: dict[str, str] = {
    "grammar": "grammar.rules",
    "lexer": "lexer.token_ext",
    "parser": "parser.pratt",
    "analyzer": "analyzer.primitives",
    "preprocessor": "preprocessor.pipeline",
    "linter": "linter.rules",
    "renderer": "renderer.doc_ir",
    "render": "render.plugins",
    "transform": "transform.slots",
    "pipeline": "pipeline.units",
    "structure": "structure.protocol",
}
# 行政段：语言包自述与 CLI 装配，不是引擎契约面（不产生能力依赖）
ADMIN_SECTIONS: frozenset[str] = frozenset(
    {"engine", "plugins", "commands", "component"}
)


def parse_use(token: str) -> tuple[str, str]:
    """`"name.vN"` → `(name, version)`；形态非法即 fail-fast。"""
    if not isinstance(token, str) or not token.strip():
        raise ConfigError(f"[engine] uses 项须为非空字符串，实得 {token!r}")
    name, _, ver = token.strip().rpartition(".v")
    if not name or not ver.isdigit():
        raise ConfigError(
            f"[engine] uses 项须为 '<能力名>.v<版本号>' 形态（如 "
            f"'lexer.token_ext.v1'），实得 {token!r}"
        )
    return name, ver


def check_uses(uses: list[str], pack_label: str) -> None:
    """逐项协商：能力须存在且版本匹配（报错**点名**是哪一项）。"""
    for token in uses:
        name, ver = parse_use(token)
        current = CAPABILITIES.get(name)
        if current is None:
            raise ConfigError(
                f"[engine] {pack_label}：引擎不认识能力 {name!r}"
                f"（已知能力: {', '.join(sorted(CAPABILITIES))}）"
            )
        if ver != current:
            raise ConfigError(
                f"[engine] {pack_label}：能力 {name!r} 声明 v{ver}，"
                f"当前引擎为 v{current}——该能力的语义已变，请按迁移说明升级语言包；"
                f"（未声明的能力变化不影响本包）"
            )


# ── 推导：语言包**实际**用到的能力（门禁据此查漏声明） ────────

def required_capabilities(pack_dir: str | Path) -> set[str]:
    """从语言包清单机械推导所需能力集（tpc.toml 段 + 能力位键 + 规则表存在性）。

    ⚠ 只扫**包自己的清单**，不猜代码：`[grammar]` 段在插件清单里同样出现，故插件
    tpc.toml 一并计入（插件是包的一部分）。
    """
    pack = Path(pack_dir)
    needed: set[str] = set()
    for tpc in sorted(pack.rglob("tpc.toml")):
        try:
            data = tomllib.loads(tpc.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:  # 配置错误由加载路径 fail-fast
            raise ConfigError(f"[engine] 读取 {tpc} 失败: {exc}") from exc
        for section in data:
            if section in ADMIN_SECTIONS:
                caps = data.get("capabilities")
                if section == "engine" and isinstance(caps, dict):
                    needed.update(f"capability.{k}" for k in caps)
                continue
            cap = SECTION_CAPABILITY.get(section)
            if cap:
                needed.add(cap)
        caps = data.get("capabilities")
        if isinstance(caps, dict):
            needed.update(f"capability.{k}" for k in caps)
    if any(pack.rglob("rules/*.toml")):
        needed.add("checks.rules")
    return needed
