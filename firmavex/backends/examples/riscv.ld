/* SPDX-License-Identifier: MIT */
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 128M }
SECTIONS {
 .text : { *(.text.start) *(.text*) *(.rodata*) } > RAM
 .data : { *(.data*) *(.sdata*) } > RAM
 PROVIDE(__global_pointer$ = . + 0x800);
 .bss : { _bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); _bss_end = .; } > RAM
 _stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
