/* ring_buffer.c — 环形缓冲实现（C 包真实语料：函数定义 + 控制流 + 表达式 + 调用）
 *
 * 用途：`tests/languages/c/test_c_corpus_impl.py` 的整文件解析样本。与
 * `ring_buffer.h` 配对：头文件验声明面，本文件验**实现面**（函数体 / 控制流 /
 * 表达式优先级 / 调用 / 指针与成员访问）。
 *
 * ⚠ 写法受**当前阶段已支持的语法面**约束（不是风格偏好，是边界）：
 *   1. 无初始化器（`int i = 0;` 属阶段 2b）→ 声明与赋值分开写；
 *   2. 无链式后缀（`r->items[i]`、`a.b.c` 见 Layer B2 的"已知边界"）→
 *      传数组指针 + 下标，或先取指针再 `->`；
 *   3. 无 `sizeof` / 强制转换 / 逗号运算符 / 预处理指令；
 *   4. `for` 不用声明式初值（`for (int i = …)` 属阶段 2b）。
 *   样本据此写成"受约束但仍是真实实现"的形态；阶段推进后本文件应逐步放宽。
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
    return n;
}

int ring_push(struct ring_item *items, unsigned int *head, unsigned int tail) {
    unsigned int next;
    struct ring_item *slot;
    next = *head + 1;
    if (next >= 16) {
        next = 0;
    }
    if (next == tail) {
        return RING_FULL;
    }
    slot = items + *head;
    slot->key = 0;
    *head = next;
    return RING_OK;
}

int ring_pop(struct ring_item *items, unsigned int head, unsigned int *tail, struct ring_item *out) {
    if (head == *tail) {
        return RING_EMPTY;
    }
    *out = items[*tail];
    *tail = *tail + 1;
    if (*tail >= 16) {
        *tail = 0;
    }
    return RING_OK;
}

unsigned int ring_sum(struct ring_item *items, int n) {
    unsigned int total;
    struct ring_item *p;
    int i;
    total = 0;
    p = items;
    for (i = 0; i < n; i++) {
        total += p->key;
        p++;
    }
    return total;
}

int ring_find(struct ring_item *items, int n, unsigned int want) {
    int i;
    int found;
    struct ring_item *p;
    found = 0;
    i = 0;
    p = items;
    while (i < n) {
        if (p->key == want) {
            found = 1;
            goto done;
        }
        i++;
        p++;
    }
done:
    return found;
}

unsigned int ring_total(struct ring_item *items, int n) {
    unsigned int total;
    total = ring_sum(items, n);
    return total;
}

int ring_scan(struct ring_item *items, int n, unsigned int want) {
    int i;
    int hits;
    struct ring_item *p;
    hits = 0;
    i = 0;
    p = items;
    do {
        switch (p->key) {
            case 0:
                break;
            case 2:
                hits += 1;
                break;
            default:
                hits += 2;
        }
        i++;
        p++;
    } while (i < n);
    return hits;
}
