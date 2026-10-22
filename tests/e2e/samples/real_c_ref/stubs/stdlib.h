/* tpc C 真实语料 harness 专用最小头——不是 libc 实现，勿用于生产。 */
void *malloc(size_t n);
void *calloc(size_t n, size_t sz);
void *realloc(void *p, size_t n);
void free(void *p);
void exit(int code);
int atoi(const char *s);
double strtod(const char *s, char **end);
long strtol(const char *s, char **end, int base);
