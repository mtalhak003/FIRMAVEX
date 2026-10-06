#include <stdint.h>

uint32_t benchmark_condition(uint32_t input)
{
    /* Unsigned arithmetic is defined; the evaluation domain is 0..255. */
    return input * 3u + 2u == 35u;
}
