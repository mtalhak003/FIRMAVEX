#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    return x[0] > x[1] && ((x[0] + x[1]) & 3u) == 1u
        && x[2] >= 5u && x[2] <= 10u && x[3] == x[0] - x[1]
        && x[3] <= 4u;
}
