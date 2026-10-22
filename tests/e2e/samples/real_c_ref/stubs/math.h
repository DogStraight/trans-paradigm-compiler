/* tpc C 真实语料 harness 专用最小头——不是 libc 实现，勿用于生产。 */
double fabs(double x);
double floor(double x);
double pow(double x, double y);
double sqrt(double x);
#define INFINITY 1e308
#define NAN (1e308*0.0)
