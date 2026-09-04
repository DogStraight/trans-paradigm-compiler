# transform — AST 变换（配置驱动 + 插件，AST → AST）

> 语义映射 + 变换由 `grammar/` 声明（[transform] 原语/映射表），插件扩展
> （typed_ports 展开 / sim 剥离等），引擎骨架语言无关。

| 文件 | 一句话 |
|------|--------|
| `engine.py` | AstTransformer + TransformPlugin 基类 + 自动注册（注释迁移 `migrate_comments`） |
| `config_driven.py` | 配置驱动变换（原语扩展：emit/expand/delete 等） |
| `_semantic_mapping.py` | 语义映射表构建 + 后处理管线 |
| `normalizer.py` | 统一的 AST 规范化层（结构保留） |
| `primitives/` | 变换原语 |

> 变换时注释迁移（旧子树注释随替换结构走）在 `engine.py::migrate_comments`。
