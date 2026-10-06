#include <stdint.h>

uint32_t benchmark_condition(uint32_t input)
{
    return (input & 0x0fu) == 0x0au;
}
