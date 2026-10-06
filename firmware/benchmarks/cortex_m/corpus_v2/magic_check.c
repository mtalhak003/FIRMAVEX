#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    return x[0] == 13u && x[1] == 2u && x[2] == 9u
        && x[3] == ((x[0] + x[1] + x[2]) ^ 7u) % 16u;
}
