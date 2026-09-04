"""组件系统协议常量 — 统一 magic string，消除静默失败。

所有组件间数据传递的 key 在此声明，拼写错误立刻可见。
Doc: core/component_protocol.md（组件元数据协议）
"""

# ── 符号属性（sym.attrs 中的 key）──
ATTR_REF_CALLBACKS = "_ref_callbacks"
"""存储引用解析回调列表。"""

ATTR_RESOLVED_PORTS = "resolved_ports"
"""存储解析后的端口列表。"""

ATTR_TYPE_DECL = "_type_decl"
"""存储对应的 TypeDecl 节点引用。"""

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
PRIMITIVE_RESOLVE_REFS = "resolve_refs"
PRIMITIVE_FLATTEN_PORTS = "flatten_ports"
PRIMITIVE_ATTACH_INVERT_MAP = "attach_invert_map"
