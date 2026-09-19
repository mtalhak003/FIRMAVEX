# FIRMAVEX Firmware Benchmarks

This directory contains small embedded-style C programs used to evaluate FIRMAVEX static analysis.

The benchmarks are intentionally small and controlled so that each expected result is known in advance.

## Benchmark Categories

### Safe Benchmarks

#### safe.c

Purpose:
- Represents a normal firmware program.
- Uses a fixed-size character buffer.
- Uses bounded string copying with `strncpy()`.

Expected result:
- No buffer-overflow finding.

#### memcpy_safe.c

Purpose:
- Represents a safe use of `memcpy()`.
- The destination buffer is larger than the source data.

Expected result:
- No buffer-overflow finding.

#### memcpy_fixed_size_safe.c

Purpose:
- Represents a safe fixed-size `memcpy()` operation.
- The destination buffer is larger than the number of bytes copied.

Expected result:
- No buffer-overflow finding.

### Vulnerable Benchmarks

#### buffer_overflow.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Uses a fixed-size destination buffer.
- Copies a longer string using `strcpy()`.

Expected result:
- Buffer-overflow risk should be detected.
- Severity: High.

#### format_string.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Passes a variable directly to `printf()` as the format string.

Expected result:
- Format-string risk should be detected.
- Severity: High.

#### memcpy_overflow.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Uses `memcpy()` to copy the contents of a larger source buffer into a smaller destination buffer.

Expected result:
- Buffer-overflow risk should be detected.
- Severity: High.

#### memcpy_numeric_overflow.c

Purpose:
- Represents an intentionally unsafe firmware program.
- Uses a numeric copy size larger than the destination buffer.

Expected result:
- Buffer-overflow risk should be detected.
- Severity: High.

## Ground Truth

| Benchmark | Category | Expected Finding | Severity |
|---|---|---|---|
| safe.c | Safe | No buffer overflow | None |
| memcpy_safe.c | Safe | No buffer overflow | None |
| memcpy_fixed_size_safe.c | Safe | No buffer overflow | None |
| buffer_overflow.c | Vulnerable | Buffer overflow risk | High |
| format_string.c | Vulnerable | Format-string risk | High |
| memcpy_overflow.c | Vulnerable | Buffer overflow risk | High |
| memcpy_numeric_overflow.c | Vulnerable | Buffer overflow risk | High |

## Purpose of the Benchmark Suite

The benchmark suite provides a controlled baseline for evaluating FIRMAVEX.

Each benchmark has a known expected result, allowing the analyzer to be evaluated for:

- Detection of known vulnerabilities.
- Avoidance of false positives on safe code.
- Correct vulnerability classification.
- Correct severity assignment.
- Regression testing as the analyzer becomes more advanced.

Future benchmark categories may include additional memory-safety, input-validation, integer, pointer, and embedded-specific failure patterns.
