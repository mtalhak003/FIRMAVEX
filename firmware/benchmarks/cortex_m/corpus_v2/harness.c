#include <stdint.h>

volatile uint32_t firmavex_actions[4] = {0u, 0u, 0u, 0u};
volatile uint32_t firmavex_failure = 0u;
extern uint32_t benchmark_condition(const uint32_t *actions);

__attribute__((noinline)) void benchmark_complete(void)
{
    while (1) {}
}

int main(void)
{
    uint32_t actions[4];
    for (uint32_t index = 0; index < 4u; ++index) {
        actions[index] = firmavex_actions[index];
    }
    firmavex_failure = benchmark_condition(actions);
    benchmark_complete();
    return 0;
}
