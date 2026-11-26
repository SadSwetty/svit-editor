// Синтаксична перевірка Metal-ядер як C++ (без Мака): MSL-ключові слова прибрано макросами.
#include "gpu_shared.h"
#define kernel
#define device
#define constant const
struct uint2 { unsigned x, y; };
#include "metal_kernels.metal"
int main() { return 0; }
