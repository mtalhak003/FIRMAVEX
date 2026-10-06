#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    return x[0] == 14u && x[1] == 9u && x[2] == 6u
        && x[3] == (x[0] * x[1] + x[2]) % 16u;
}
