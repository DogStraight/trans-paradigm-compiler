/* edge_comments.c — 注释落位边界样本（保真度闭环用）
 * 覆盖：文件头块注释、函数内行注释、行尾行注释、行内块注释、struct 体成员前注释、
 * 文件尾无换行注释。
 * ⚠ 本样本**只放当前能保真的落位**；已知会丢的落位（enum 体首项前的独占行注释、
 * 落在声明符后缀链/下标里的注释）记在 docs/gaps/gap-language-pack-scope.md，不进样本——
 * 样本一旦变红就说明闭环回归，而不是把已知缺口当期望。
 */

// 行注释（独立行）

struct pair {
    // 成员前注释
    int left;
    int right; // 行尾注释
};

int add(int a /* 行内块注释 */, int b) {
    /* 块注释（函数体内独立行） */
    int sum = a + b; // 行尾
    return sum;
}

/* 文件尾块注释 */
