/* SPDX-License-Identifier: MIT. Independent RV32IM virt demonstration. */
typedef unsigned int uint32_t;
volatile uint32_t input_a, input_b, failure_flag;
__attribute__((noinline)) void input_ready(void) { __asm__ volatile("nop"); }
__attribute__((noinline)) void benchmark_complete(void) { __asm__ volatile("nop"); }
void main(void) {
    failure_flag = 0;
    input_a = input_b = 0;
    input_ready();
    failure_flag = (input_a == 2 && input_b == 1);
    benchmark_complete();
    for (;;) __asm__ volatile("nop");
}
