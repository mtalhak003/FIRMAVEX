volatile unsigned int firmavex_input = 10;
volatile unsigned int firmavex_failure = 0;

int main(void)
{
    if (firmavex_input > 5)
    {
        firmavex_failure = 1;
    }

    while (1)
    {
    }
}
