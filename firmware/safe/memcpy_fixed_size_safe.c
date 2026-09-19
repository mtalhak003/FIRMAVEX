#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[8];
    char input[32] = "CodePulse";

    memcpy(buffer, input, 4);

    printf("Firmware data: %s\n", buffer);

    return 0;
}