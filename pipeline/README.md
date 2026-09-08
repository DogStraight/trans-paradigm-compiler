# pipeline — 管线编排

> 各阶段（lexer→…→renderer）的编排入口，层间数据形态/阻断语义见
> `docs/pipeline_stages.md`；analyze/transform 的 pass 时点编排见 `schedule.py`
> + `docs/pipeline_stages.md`（编排调度）。

| 文件 | 一句话 |
|------|--------|
| `__init__.py` | 管线编排（`run_pipeline_on_source`，阶段序列化执行） |
| `schedule.py` | 编排调度：pass 声明 + 时点序列器 + 调度构建 |
