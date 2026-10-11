#include <stdint.h>

volatile uint32_t product_inputs[2];
volatile uint32_t product_failure;
volatile uint32_t initialized_data = 0x13579bdf;

__attribute__((noinline)) void product_input_ready(void)
{
    __asm__ volatile ("nop");
}

__attribute__((noinline)) void product_complete(void)
{
    __asm__ volatile ("nop");
}

int main(void)
{
    /* Deliberately clear inputs after reset: injection must follow startup. */
    product_inputs[0] = 0;
    product_inputs[1] = 0;
    product_failure = 0;
    product_input_ready();
    if (initialized_data == 0x13579bdf &&
        product_inputs[0] == 2 && product_inputs[1] == 1)
        product_failure = 1;
    product_complete();
    for (;;) { __asm__ volatile ("nop"); }
}
