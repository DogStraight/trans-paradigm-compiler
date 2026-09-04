# renderer — Doc IR → 格式化输出（世界 A）

> AST + 布局规则（`grammar/` TOML renderer 段）→ 文本。Doc IR + 原语 = 世界 A；
> Verilog formatter pass 管线 = 世界 B（在 `grammar/verilog/plugins/formatter/`）。
> 双世界关系与缺口见 `docs/renderer_architecture.md`。

| 文件 | 一句话 |
|------|--------|
| `doc.py` | Doc IR（漂亮打印机中间表示）+ `layout()` 布局 |
| `renderer.py` | Renderer 主类（AST + 布局规则驱动 → 文本） |
| `node_renderer.py` | 节点级渲染（含 `_comment_slots` 槽位消费：leading/trailing/inline） |
| `loader.py` | TOML 布局规则 / 风格加载 |
| `inline_comment.py` | 锚点注释回注（纯 tpc marker 通道） |
| `comment_restore.py` | 注释回插编排 |
| `fidelity.py` | 保真度分级 |
| `primitives/` | Doc 原语（text/break/line/join/align/line_suffix/suffix_when…） |

> 注释渲染：独立行 = Comment 节点；行内/行尾 = `_comment_slots`
> （leading/trailing/inline/inline_after），见 `docs/MODEL_INDEX.md`「跨子系统」。
