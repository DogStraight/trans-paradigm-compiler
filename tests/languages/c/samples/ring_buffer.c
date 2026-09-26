/* ring_buffer.c — 环形缓冲实现（C 包真实语料：函数定义 + 控制流 + 表达式 + 调用）
 *
 * 用途：`tests/languages/c/test_c_corpus_impl.py` 的整文件解析样本。与
 * `ring_buffer.h` 配对：头文件验声明面，本文件验**实现面**（函数体 / 控制流 /
 * 表达式优先级 / 调用 / 指针与成员访问）。
 *
 * ⚠ 写法受**当前阶段已支持的语法面**约束（不是风格偏好，是边界）：
 *   1. 无强制转换 / 逗号运算符 / 预处理指令。
 *   ✅ **已放宽**（阶段 2b / 3 到位，本文件随能力"长回"自然写法）：声明即初始化、
 *   `for (int i = 0; …)` 声明式初值、**指示符初始化 `.field=`/`[i]=`**、**`sizeof`**、
 *   **链式后缀**（`r->items[i].key` / `f(x)[i]` / `p->q->r`，C99 §6.5.2）。
 *   样本随阶段推进持续放宽；**不要**为了让样本"好看"而使用未支持的语法。
 */

typedef unsigned long size_alias;

enum ring_status { RING_OK, RING_FULL = 2, RING_EMPTY };

struct ring_item {
    unsigned int key;
    const char *name;
    int values[4];
};

typedef struct ring_item ring_item;

struct ring {
    struct ring_item items[16];
    unsigned int head;
    unsigned int tail;
};

/* 用上阶段 2b 的指示符初始化与 sizeof（真实代码里的常见写法） */
int ring_marks[4] = {[0] = 1, [3] = 2};

unsigned int ring_item_size = sizeof(struct ring_item);

/* 字符串转义（C99 §6.4.4.4）：`\"` 不再提前收尾——`[string] escape` 段级声明 */
const char *ring_banner = "say \"hi\"";

static const struct ring_item ring_default = {.key = 0, .values = {[1] = 7}};

int ring_init(struct ring *r) {
    r->head = 0;
    r->tail = 0;
    return 0;
}

static int ring_count(struct ring *r) {
    int n;
    n = r->head - r->tail;
    if (n < 0) {
        n = n + 16;
    }
    /* 链式后缀（C99 §6.5.2）：`->` + 下标 + `.` 三级串起来 */
    if (r->items[r->head].key == 0) {
        n = n + 1;
    }
    return n;
}

int ring_push(struct ring *r, struct ring_item *item) {
    unsigned int next = r->head + 1;
    if (next >= 16) {
        next = 0;
    }
    if (next == r->tail) {
        return RING_FULL;
    }
    r->items[r->head] = *item;
    r->head = next;
    return RING_OK;
}

int ring_pop(struct ring *r, struct ring_item *out) {
    if (r->head == r->tail) {
        return RING_EMPTY;
    }
    /* 链式后缀三级：`->` + 下标 + `.`；调用结果再下标见 `ring_sum` */
    *out = r->items[r->tail];
    r->tail = r->tail + 1;
    if (r->tail >= 16) {
        r->tail = 0;
    }
    return RING_OK;
}

void ring_reset(struct ring *r) {
    r->head = 0;
    r->tail = 0;
}

unsigned int ring_sum(struct ring *r, int n) {
    unsigned int total = 0;
    for (int i = 0; i < n; i++) {
        total += r->items[i].key;
    }
    return total;
}

int ring_find(struct ring *r, int n, unsigned int want) {
    int i = 0;
    int found = 0;
    while (i < n) {
        if (r->items[i].key == want) {
            found = 1;
            goto done;
        }
        i++;
    }
done:
    return found;
}

unsigned int ring_total(struct ring *r, int n) {
    unsigned int total;
    total = ring_sum(r, n);
    return total;
}

int ring_scan(struct ring *r, int n, unsigned int want) {
    int i = 0;
    int hits = 0;
    do {
        switch (r->items[i].key) {
            case 0:
                break;
            case 2:
                hits += 1;
                break;
            default:
                hits += 2;
        }
        i++;
    } while (i < n);
    return hits;
}
