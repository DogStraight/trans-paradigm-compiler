"""analyzer/elaboration — 精化协议（引擎侧契约 + 驱动器，语言无关）。

> 定案见 `docs/decisions/0019-elaboration-plugin-protocol.md`；文件职责见 `README.md`。
> 本包**只提供机制**：项列表与全部语义求解都归语言包插件
> （`grammar/<lang>/plugins/elaboration/`，`[capabilities] elaborator`）。

命名纪律：中文行文称"精化"，但部件/类名/能力名一律用 `elaboration`
（避免与 refinement（B/Event-B 规格精化）撞词）。
"""

from analyzer.elaboration.atoms import StructureAtomSource
from analyzer.elaboration.contract import (
    SCOPE_FILE,
    SCOPE_PROJECT,
    SCOPE_UNIT,
    SCOPES,
    ElaborationItem,
    ElaboratorSpec,
    Locator,
    parse_spec,
)
from analyzer.elaboration.driver import (
    Atom,
    AtomSource,
    ElaborationResult,
    Elaborator,
    SolveCtx,
)
from analyzer.elaboration.loader import CAPABILITY_NAME, load_elaborator_spec
from analyzer.elaboration.service import ElaborationService, ServiceApi

__all__ = [
    "CAPABILITY_NAME",
    "SCOPE_FILE",
    "SCOPE_PROJECT",
    "SCOPE_UNIT",
    "SCOPES",
    "Atom",
    "AtomSource",
    "ElaborationItem",
    "ElaborationResult",
    "ElaborationService",
    "Elaborator",
    "ElaboratorSpec",
    "Locator",
    "ServiceApi",
    "SolveCtx",
    "StructureAtomSource",
    "load_elaborator_spec",
    "parse_spec",
]
