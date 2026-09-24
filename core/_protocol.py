"""组件系统协议常量 — 统一 magic string，消除静默失败。

所有组件间数据传递的 key 在此声明，拼写错误立刻可见。
Doc: core/component_protocol.md（组件元数据协议）
"""

# ── 符号属性（sym.attrs 中的 key）──
ATTR_RESOLVED_PORTS = "resolved_ports"
"""存储解析后的端口列表。"""

ATTR_TYPE_DECL = "_type_decl"
"""存储对应的 TypeDecl 节点引用。"""

# ── 展开行字段（映射表来源追踪）──
ROW_ORIGIN = "origin"
"""展开行的来源路径（可视化管道：映射表来源追踪，ADR-0015 §2）。

由展开侧（组件，如 typed_ports `_expand_ports`）写入 `resolved_ports` 行，
引擎侧（SemanticMappingPlugin）按此键收集来源做可视化，不解析语义——
引擎只认协议字段名，不懂段含义（语言知识不进引擎）。"""

# ── 变换槽位（[[transform.slots]] 声明）──
SLOT_CTX_SELF = "$node"
"""槽位 ctx 来源特殊值：触发节点自身（其余值 = 子树内首个同名节点）。"""

# ── 映射表（SemanticMappingPlugin 产出的表名）──
TABLE_TYPE_PORTS_FLAT = "type_ports_flat"
"""类型化端口的扁平端口列表。"""

TABLE_IMPL_BINDING = "impl_binding"
"""impl 绑定关系。"""

TABLE_TYPE_MAP = "type_map"
"""类型声明与实现的映射。"""

# ── 共享上下文（AstTransformer._shared_ctx 中的 key）──
CTX_RULES = "rules"
"""语法规则 dict。"""

CTX_MAPPING_CFG = "mapping_cfg"
"""映射表配置。"""

CTX_EXTRA_ASTS = "_remapper_extra_asts"
"""额外 AST 输出列表。"""

# ── 精化产物容器（context.extra 中的 key；ADR-0019）──
CTX_ELABORATION = "elaboration"
"""精化产物容器：`{容器键: {原子键: 值}}`。

引擎只定**容器与生命周期**；容器键（= 精化项的 `provides`）与值形状由语言包定义
（`analyzer/elaboration/` 引擎不解释语义）。未声明精化能力 → 本键不出现（降级）。"""

CTX_ANALYZED_FILE = "analyzed_file"
"""**当前分析文件**的路径（`context.extra` 中的 key）。

插件 postpass 需要知道"我正在分析哪个文件"，才能按文件取精化产物的**切片**
（如 `容器["connections"][本文件]`）。这是**语言无关的文件层事实**（引擎给出的当前
文件路径），不是语言知识——故由引擎注入，而不是让插件去猜/反查 AST。"""

# ── 组件元数据 key（component.toml 字段名）──
META_NAME = "name"
META_LANG = "lang"
META_DESC = "description"
META_REQUIRES = "requires"
META_GRAMMAR = "grammar"
META_ANALYZER = "analyzer"
META_TRANSFORM = "transform"
META_RENDER = "render"

# ── 分析器原语名称（builtins 组件注册）──
PRIMITIVE_SCOPE_ENTER = "scope_enter"
PRIMITIVE_SCOPE_EXIT = "scope_exit"
PRIMITIVE_SYMBOL_DECLARE = "symbol_declare"
PRIMITIVE_IDENTIFIER_RESOLVE = "identifier_resolve"
