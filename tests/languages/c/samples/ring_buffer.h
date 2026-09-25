/* ring_buffer.h — 固定容量环形缓冲的最小接口（真实风格头文件）
 *
 * 用途：C 包的**真实语料**样本（`tests/languages/c/test_c_corpus.py`）。
 * 写法刻意贴近真实工程头文件：多级 typedef、聚合类型、位宽数组、
 * 跨 struct 的指针参数、枚举带显式值、混合存储类。
 *
 * ⚠ 不含预处理指令（`#ifndef` / `#define` / `#include`）——C 的预处理属阶段 4，
 *   本包尚未接（见 docs/gaps/gap-language-pack-scope.md）。样本范围随阶段推进扩大。
 * ⚠ 数组长度用数字字面量（长度用宏/常量表达式属阶段 2b/3）。
 */

typedef unsigned long size_alias;

enum ring_status { RING_OK, RING_FULL = 2, RING_EMPTY };

struct ring_item {
    unsigned int key;
    const char *name;
    int values[4];
};

typedef struct ring_item ring_item;

union ring_slot {
    int i;
    float f;
    char bytes[8];
};

struct ring {
    struct ring_item items[16];
    unsigned int head;
    unsigned int tail;
};

extern int ring_init(struct ring *r);

int ring_push(struct ring *r, struct ring_item *item);

int ring_pop(struct ring *r, struct ring_item *out);

void ring_reset(struct ring *r);

static int ring_count(struct ring *r);
