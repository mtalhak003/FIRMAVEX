#include <stdint.h>

/* Instrumentation-only fixture: both branches are non-triggering. */
volatile uint32_t runtime_sink = 0u;

uint32_t benchmark_condition(const uint32_t *actions)
{
    if (actions[0] == 0u) {
        runtime_sink = 1u;
    } else {
        for (uint32_t index = 0u; index < 3u; ++index) {
            runtime_sink += index + actions[0];
        }
    }
    return 0u;
}
