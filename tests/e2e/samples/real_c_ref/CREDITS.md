# 真实 C 语料归属与许可（real_c_ref）

本目录是 C 包真实语料门禁（`PROGRESS.md` 退出判据 5）的语料：来源、版本与许可如下。
所有源文件**保留原始版权/许可头**（cJSON 的 MIT 全文在 `ref/cJSON.c`、`ref/cJSON.h` 头注；
zlib license 全文在 `ref/zlib.h` 头注），本文件只记来源与版本。

## 来源与版本

| 文件 | 来源 | 版本 | 许可 |
|---|---|---|---|
| `ref/cJSON.c` / `ref/cJSON.h` | https://github.com/DaveGamble/cJSON | 1.7.19（源内 `CJSON_VERSION_*`） | MIT |
| `ref/zlib.h` / `ref/zconf.h` / `ref/zutil.h` / `ref/gzguts.h` | https://github.com/madler/zlib | 1.3.2（`zlib.h` 头注，2026-02-17） | zlib license |
| `ref/zutil.c` / `ref/crc32.c` / `ref/adler32.c` / `ref/compress.c` / `ref/uncompr.c` / `ref/gzread.c` | 同上 | 同上 | 同上 |

- 只入 cJSON 核心 2 文件 + zlib 6 个 C 文件与所需 4 个头（`zlib.h`/`zconf.h`/`zutil.h`/`gzguts.h`）；
  zlib 的 `crc32.h` 是 `crc32.c` 生成的**大表产物**（591KB，未被任何文件 include）⇒ 不入库。
- 语料仅用于解析/诊断回归，不编译、不链接。

## stubs/

`stubs/` 是 14 个**最小系统头**（`stdio.h`/`stdlib.h`/`string.h`/`math.h`/`limits.h`/
`float.h`/`ctype.h`/`locale.h`/`stddef.h`/`stdarg.h`/`stdint.h`/`stdbool.h`/`fcntl.h`/
`errno.h`）——只含语料用到的 typedef/原型/宏，供 `ProjectChecker(include_dirs=[ref, stubs])`
跑通 include 面。**不是 libc 实现**，每个文件头注已标明；`fcntl.h`/`errno.h` 为空占位
（zlib 条件编译探测用）。

## 语料边界

- 语料是**合法 C**（gcc 编译无错；oracle 见 `docs/gaps/gap-c-real-corpus.md`）；本门禁的
  目标是"诊断计数只许减不许增"，基线 = **0 诊断**（语法 0 + 语义 0，2026-10-23 T1 后实测）。
- 若上游语料更新，须同步更新上表版本并重跑基线（`python tests/e2e/eval_diag_baseline_c.py --update`），
  在提交说明原因。
