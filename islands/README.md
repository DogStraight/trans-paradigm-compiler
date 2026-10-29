# islands — 片段模式（语法配置驱动的岛式分片）

> 片段模式 = 把源文本按**语法配置推导出的语法岛**切开，每个岛进真实管线，再按原位置
> 合成；未被岛覆盖的区间（water）逐字节原样保留。**无岛声明、无记号、无范围可选模式**
> （作者 2026-10-30 定稿）：片段模式下语言包语法推导出的语法单元默认就是岛；要限定
> "只有某部分语法有效"，单开一个语言包。

## 文件

| 文件 | 一句话 |
|------|--------|
| `model.py` | 装配岛模型：复用 `linter` 内部推导组件（LinterScanner 的 lexer + discovery），零语言字面量 |
| `segment.py` | token 区间 → 字符区间、water 判据（未覆盖/未识别/含宏区间）、行首缩进 |
| `process.py` | 岛文本 → 真实管线（parse+render+formatter）→ 片段文本；后验 = 重解析 + 双跑逐字幂等 |
| `splice.py` | 编辑集从右向左应用 + 缩进基线回填（首行不补：行首缩进留在 water） |
| `rewrite.py` | 主编排：bytes → 岛树 → 自顶向下处理 → 合成 → bytes；无岛逐字节 identity |

## 契约要点

- **自顶向下**：节点过管线成功 ⇒ 整段替换、不再处理子节点；失败递归子节点；仍失败 ⇒
  该区间落 water（"能解析/能变换的部分进管线，其余原样"）。
- **岛内只走真实管线**：默认管线面 = format 等价（parse + render + formatter 插件；
  analyze/transform 关闭，岛缺岛外上下文）。
- **fail-closed**：岛管线/后验失败按 water 原样保留，不落编辑、不崩溃；无岛/零变化 ⇒
  **逐字节**返回原 bytes（BOM/CRLF/无尾换行保真）。
- **可复跑**：同一输入两次改写结果一致（岛级双跑幂等 + 整个文件改写幂等）。

## 运行

```
python main.py fragment 文件.v            # dry-run diff + 摘要
python main.py fragment 文件.v --write    # 落盘
python main.py fragment 文件.c --rules-dir grammar/c
```

## 验证

`tests/engine/test_islands.py`（identity / BOM+CRLF / 岛处理 / water 保留 / 宏落水 /
双跑幂等 / C 包同机制）。片段模式不改变 `format` 等既有命令的默认行为。

Doc: `docs/gaps/gap-fragment-mode.md`（契约、实测边界、P2/P3 退出判据）
