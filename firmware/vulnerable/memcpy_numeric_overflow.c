#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[8];
    char input[32] = "CodePulse-Numeric-Overflow";

    memcpy(buffer, input, 16);

    printf("Firmware data: %s\n", buffer);

    return 0;
}