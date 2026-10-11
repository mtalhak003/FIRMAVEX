ENTRY(Reset_Handler)
MEMORY {
    FLASH (rx) : ORIGIN = 0x00000000, LENGTH = 4M
    RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 4M
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
    .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
    .text : { *(.text*) *(.rodata*) } > FLASH
    .data : {
        _sdata = .; *(.data*) . = ALIGN(4); _edata = .;
    } > RAM AT> FLASH
    _sidata = LOADADDR(.data);
    .bss (NOLOAD) : {
        . = ALIGN(4); _sbss = .; *(.bss*) *(COMMON)
        . = ALIGN(4); _ebss = .;
    } > RAM
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }
}
