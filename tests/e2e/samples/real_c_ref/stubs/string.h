/* tpc C 真实语料 harness 专用最小头——不是 libc 实现，勿用于生产。 */
size_t strlen(const char *s);
char *strcpy(char *d, const char *s);
char *strncpy(char *d, const char *s, size_t n);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
void *memcpy(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
char *strchr(const char *s, int c);
