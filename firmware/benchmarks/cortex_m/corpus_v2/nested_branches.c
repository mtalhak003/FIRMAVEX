#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    if (x[0] >= 10u) {
        if (x[1] < x[0]) {
            if (x[2] == x[0] - x[1]) {
                if (x[3] == x[2] + 1u) return 1u;
            }
        }
    }
    return 0u;
}
