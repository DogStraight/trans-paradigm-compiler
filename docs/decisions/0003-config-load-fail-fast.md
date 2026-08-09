# ADR-0003: 配置加载 fail-fast（不静默吞损坏配置）

- Status: accepted
- Date: 2026-08-09

## 背景

token.toml 重复 key 事故：`[id.keyword]` 出现重复键 → TOML 解析失败 → `ConfigRegistry.load_all` 的 `except Exception` 把它当"可选缺失"静默存 `{}` → `token_lang`（required=false）损坏 → `id.keyword` 空 → **全部 token 退化为 id**（module/always/begin 全变 id，linter 全面崩溃）。静默错乱是"假绿"温床。

## 决策

`load_all` 分三类异常处理：
- `TOMLDecodeError` → 一律 fail-fast（含 required=False）
- 缺声明 section → KeyError fail-fast（不再 `data.get(section,{})` 静默空表）
- 非"文件缺失"异常 → 统一 fail-fast
- 仅 `FileNotFoundError` + required=False → 容忍

`lexer/lexer_utils.py` `get_token_define_merged` 加 `_validate_token_define` 结构自检（关键段 symbol/space/newline/bracket/id 存在 + `id.keyword` 非空）。

## 权衡

- 代价：配置损坏时启动即报错（fail-fast 的"不友好"）。
- 换取：杜绝"空表→全退化为 id"类静默错乱；防假绿；损坏在入口暴露而非运行期难查。
- 备选：静默容错（拒绝：2026-07-26 事故的直接根因）。

## 验证

tests/test_config_loading.py（4 个，save/restore 隔离注册表）；325 pytest 全过。

> Impl: core/config_registry.py::ConfigRegistry.load_all
> Impl: lexer/lexer_utils.py::get_token_define_merged
> Test: tests/test_config_loading.py
