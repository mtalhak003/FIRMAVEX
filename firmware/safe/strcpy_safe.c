#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[32];
    const char *input = "FIRMAVEX";

    strcpy(buffer, input);

    printf("Firmware data: %s\n", buffer);

    return 0;
}