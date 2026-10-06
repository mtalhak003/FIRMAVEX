#include <stdint.h>

/* QEMU loads ELF RAM sections. Do not overwrite debugger-injected input. */
volatile uint32_t firmavex_input = 0;
volatile uint32_t firmavex_failure = 0;

extern uint32_t benchmark_condition(uint32_t input);

__attribute__((noinline)) void benchmark_complete(void)
{
    while (1)
    {
    }
}

int main(void)
{
    firmavex_failure = benchmark_condition(firmavex_input);
    benchmark_complete();
    return 0;
}
