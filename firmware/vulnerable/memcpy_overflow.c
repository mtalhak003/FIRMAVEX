#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[8];
    char input[32] = "CodePulse-Memcpy-Overflow";

    memcpy(buffer, input, sizeof(input));

    printf("Firmware data: %s\n", buffer);

    return 0;
}