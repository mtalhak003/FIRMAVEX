#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    return x[0] + x[1] == 23u && x[0] >= 9u && x[1] >= 8u;
}
