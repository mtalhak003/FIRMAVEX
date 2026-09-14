#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[8];
    const char *input = "CodePulse-Overflow";

    strcpy(buffer, input);

    printf("Firmware data: %s\n", buffer);

    return 0;
}
