#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    return ((((x[0] << 2u) ^ x[1]) + x[2]) & 31u) == 27u
        && x[3] == (x[0] ^ x[2]);
}
