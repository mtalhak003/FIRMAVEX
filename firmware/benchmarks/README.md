# CodePulse Firmware Benchmarks

This directory contains small embedded-style C programs used to evaluate CodePulse.

## Benchmark Categories

### Safe

safe/safe.c

Purpose:
- Represents a normal firmware program.
- Uses a fixed-size character buffer.
- Uses bounded string copying.
- Expected result: no buffer-overflow finding.

#### memcpy_safe.c

Purpose:
- Represents a safe use of memcpy().
- The destination buffer is larger than the source data.
- Expected result: no buffer overflow finding.
### Vulnerable

#### buffer_overflow.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Uses a fixed-size buffer.
- Copies a longer string using strcpy().
- Expected result: buffer-overflow risk should be detected.
#### memcpy_overflow.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Uses a fixed-size destination buffer.
- Copies more data than the destination buffer can safely hold.
- Expected result: buffer-overflow risk should be detected.
#### format_string.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Passes user-controlled or variable data directly to printf().
- Expected result: format-string risk should be detected.
## Ground Truth

| Benchmark | Expected Finding | Severity |
|---|---|---|
| safe.c | No buffer overflow | None |
| buffer_overflow.c | Buffer overflow risk | High |
| format_string.c | Format-string risk | High |
| memcpy_overflow.c | Buffer overflow risk | High |
| memcpy_safe.c | No buffer overflow | None |