#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    uint32_t accumulator = 0u;
    for (uint32_t index = 0; index < 4u; ++index) {
        accumulator = accumulator * 3u + x[index];
    }
    return x[0] == 7u && accumulator == 287u;
}
