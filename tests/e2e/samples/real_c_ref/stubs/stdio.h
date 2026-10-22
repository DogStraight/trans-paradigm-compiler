/* tpc C 真实语料 harness 专用最小头——不是 libc 实现，勿用于生产。 */
typedef struct tpc_file_stub FILE;
extern FILE *stdin;
extern FILE *stdout;
extern FILE *stderr;
int printf(const char *fmt);
int fprintf(FILE *f, const char *fmt);
int sprintf(char *s, const char *fmt);
int snprintf(char *s, size_t n, const char *fmt);
int vsnprintf(char *s, size_t n, const char *fmt, va_list ap);
int fputs(const char *s, FILE *f);
int fputc(int c, FILE *f);
FILE *fopen(const char *path, const char *mode);
int fclose(FILE *f);
size_t fread(void *p, size_t sz, size_t n, FILE *f);
int fseek(FILE *f, long off, int whence);
long ftell(FILE *f);
int feof(FILE *f);
