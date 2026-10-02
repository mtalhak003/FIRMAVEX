#include <stdint.h>

extern int main(void);
extern uint32_t _estack;

void Reset_Handler(void);
void Default_Handler(void);

__attribute__((section(".isr_vector")))
const void *vector_table[] =
{
    (void *)&_estack,
    (void *)Reset_Handler
};

void Reset_Handler(void)
{
    main();

    while (1)
    {
    }
}

void Default_Handler(void)
{
    while (1)
    {
    }
}
