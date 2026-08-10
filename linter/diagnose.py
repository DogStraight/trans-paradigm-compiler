"""linter/diagnose.py — 多路径诊断：枚举条件编译所有路径并逐条 lint 汇总。

用于覆盖"不同编译选项下不同结构"的多义性文本。默认单枚举（scan）只检当前
条件路径；多路径诊断（diagnose_all_paths）展开条件块的所有叶分支路径，
逐条生成单版本文本并 lint，汇总带条件来源标注的诊断。

不编码语言知识：条件结构来自 preprocessor 的 condition_blocks，注入参数
predefined/undefine 直接透传 scan_directives。
"""

from preprocessor._expand import scan_directives, enumerate_conditions
from linter.scanner import LinterScanner


def diagnose_all_paths(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    search_dirs: list[str] | None = None,
    predefined: dict[str, str] | None = None,
    undefine: set[str] | None = None,
    max_configs: int | None = None,
) -> list[dict]:
    """多路径诊断：枚举条件块叶路径，逐条生成单版本文本并 lint。

    Returns: list[dict]，每项
        {"define": list[str], "undefine": list[str], "diagnostics": [LintDiagnostic]}
    define/undefine 为该路径的条件注入（来源标注），diagnostics 为该路径下
    LinterScanner.scan 的诊断结果。
    """
    # 基础扫描：拿条件块结构（不展开）
    _, _, blocks, _, _, _ = scan_directives(
        source,
        rules_dir,
        source_path=source_path,
        search_dirs=search_dirs,
        predefined=predefined,
        undefine=undefine,
    )
    configs = enumerate_conditions(blocks, max_configs)

    scanner = LinterScanner(rules_dir=rules_dir)
    results = []
    for cfg in configs:
        d = dict(predefined or {})
        d.update({name: "1" for name in cfg["define"]})
        u = set(undefine or ())
        u |= cfg["undefine"]
        diags = scanner.scan(
            source,
            predefined=d or None,
            undefine=u or None,
        )
        results.append(
            {
                "define": sorted(cfg["define"]),
                "undefine": sorted(cfg["undefine"]),
                "diagnostics": diags,
            }
        )
    return results
