#include <stdio.h>
#include <string.h>

int main(void)
{
    char buffer[32];
    char input[8] = "FIRMAVEX";

    memcpy(buffer, input, sizeof(input));

    printf("Firmware data: %s\n", buffer);

    return 0;
}
