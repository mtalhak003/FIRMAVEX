#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[16];
    const char *message = "CodePulse";

    strncpy(buffer, message, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';

    printf("Firmware message: %s\n", buffer);

    return 0;
}
