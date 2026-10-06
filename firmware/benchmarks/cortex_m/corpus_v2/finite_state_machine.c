#include <stdint.h>

uint32_t benchmark_condition(const uint32_t *x)
{
    uint32_t state = 0u;
    for (uint32_t index = 0; index < 4u; ++index) {
        uint32_t action = x[index];
        switch (state) {
        case 0: state = action == 6u ? 1u : 0u; break;
        case 1: state = (action == 3u || action == 4u) ? 2u : 0u; break;
        case 2: state = action == 12u ? 3u : 0u; break;
        case 3: if (action == 9u || action == 10u) return 1u;
                state = 0u; break;
        }
    }
    return 0u;
}
