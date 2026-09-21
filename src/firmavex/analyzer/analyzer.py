from pathlib import Path
import re


DANGEROUS_FUNCTIONS = {
    "strcpy": "Potential buffer overflow",
    "strcat": "Potential buffer overflow",
    "gets": "Potential buffer overflow",
    "sprintf": "Potential buffer overflow",
}


FORMAT_FUNCTIONS = {
    "printf",
    "fprintf",
    "sprintf",
}


MEMORY_FUNCTIONS = {
    "memcpy",
    "memmove",
}


def remove_comments_and_strings(source_code: str) -> str:
    """
    Remove C comments and string literals while preserving line structure.

    Newlines are preserved so that analyzer findings keep their
    original source-code line numbers.
    """

    # Remove multiline comments while preserving newlines.
    source_code = re.sub(
        r"/\*.*?\*/",
        lambda match: "\n" * match.group(0).count("\n"),
        source_code,
        flags=re.DOTALL,
    )

    # Remove single-line comments.
    source_code = re.sub(
        r"//.*",
        "",
        source_code,
    )

    # Remove C string literals while preserving their line count.
    source_code = re.sub(
        r'"(?:\\.|[^"\\])*"',
        lambda match: "",
        source_code,
    )

    return source_code


def find_buffer_sizes(source_code: str) -> dict:
    """
    Find simple character-array declarations and their sizes.

    Example:
        char buffer[8];

    Returns:
        {
            "buffer": 8
        }
    """

    buffer_sizes = {}

    pattern = r"\bchar\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]"

    for match in re.finditer(pattern, source_code):
        variable_name = match.group(1)
        size = int(match.group(2))

        buffer_sizes[variable_name] = size

    return buffer_sizes


def find_string_sizes(source_code: str) -> dict:
    """
    Find simple constant string declarations and their lengths.

    Example:
        const char *input = "FIRMAVEX";

    Returns:
        {
            "input": 9
        }

    The length includes the null terminator.
    """

    string_sizes = {}

    pattern = (
        r"\b(?:const\s+)?char\s*\*\s*"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r'"((?:\\.|[^"\\])*)"'
    )

    for match in re.finditer(pattern, source_code):
        variable_name = match.group(1)
        string_value = match.group(2)

        string_sizes[variable_name] = len(string_value) + 1

    return string_sizes


def analyze_firmware(source_file: str) -> dict:
    """
    Perform a basic static analysis of a C source file.

    Returns:
    - success: whether analysis completed
    - source_file: analyzed source file
    - findings: detected security issues
    - error: error message if analysis failed
    """

    source = Path(source_file)

    if not source.exists():
        return {
            "success": False,
            "source_file": str(source),
            "findings": [],
            "error": f"Source file not found: {source}",
        }

    try:
        source_code = source.read_text(encoding="utf-8")
    except OSError as error:
        return {
            "success": False,
            "source_file": str(source),
            "findings": [],
            "error": str(error),
        }

    cleaned_code = remove_comments_and_strings(source_code)

    buffer_sizes = find_buffer_sizes(cleaned_code)
    string_sizes = find_string_sizes(source_code)

    findings = []

    for line_number, line in enumerate(
        cleaned_code.splitlines(),
        start=1,
    ):
        # Check dangerous functions such as strcpy().
        for function_name, description in DANGEROUS_FUNCTIONS.items():
            pattern = rf"\b{re.escape(function_name)}\s*\("

            if not re.search(pattern, line):
                continue

            # strcpy() receives special handling when the source is a
            # known constant string and the destination is a known buffer.
            if function_name == "strcpy":
                strcpy_match = re.search(
                    r"\bstrcpy\s*\(\s*"
                    r"([A-Za-z_][A-Za-z0-9_]*)"
                    r"\s*,\s*"
                    r"([A-Za-z_][A-Za-z0-9_]*)"
                    r"\s*\)",
                    line,
                )

                if strcpy_match:
                    destination = strcpy_match.group(1)
                    source_variable = strcpy_match.group(2)

                    destination_size = buffer_sizes.get(destination)
                    source_size = string_sizes.get(source_variable)

                    # If both sizes are known, report only when the
                    # complete string including '\0' exceeds the buffer.
                    if (
                        destination_size is not None
                        and source_size is not None
                    ):
                        if source_size <= destination_size:
                            continue

                    # If the source/destination cannot be proven safe,
                    # continue to report the potential vulnerability.
                else:
                    # Keep the existing conservative behavior for
                    # unrecognized strcpy() patterns.
                    pass

            findings.append(
                {
                    "type": description,
                    "function": function_name,
                    "line": line_number,
                    "code": line.strip(),
                    "severity": "High",
                }
            )

        # Check for direct variable use as a format string.
        for function_name in FORMAT_FUNCTIONS:
            pattern = (
                rf"\b{re.escape(function_name)}"
                rf"\s*\(\s*"
                rf"([A-Za-z_][A-Za-z0-9_]*)"
                rf"\s*\)"
            )

            if re.search(pattern, line):
                findings.append(
                    {
                        "type": "Potential format string vulnerability",
                        "function": function_name,
                        "line": line_number,
                        "code": line.strip(),
                        "severity": "High",
                    }
                )

        # Check memory-copy functions such as memcpy() and memmove().
        for function_name in MEMORY_FUNCTIONS:
            pattern = (
                rf"\b{re.escape(function_name)}"
                rf"\s*\(\s*"
                rf"([A-Za-z_][A-Za-z0-9_]*)"
                rf"\s*,\s*"
                rf"([A-Za-z_][A-Za-z0-9_]*)"
                rf"\s*,\s*"
                rf"(.+?)"
                rf"\s*\)\s*;"
            )

            match = re.search(pattern, line)

            if not match:
                continue

            destination = match.group(1)
            source = match.group(2)
            size_expression = match.group(3).strip()

            destination_size = buffer_sizes.get(destination)

            if destination_size is None:
                continue

            copy_size = None

            # Case 1:
            # memcpy(buffer, input, sizeof(input));
            sizeof_match = re.fullmatch(
                r"sizeof\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
                size_expression,
            )

            if sizeof_match:
                size_variable = sizeof_match.group(1)
                copy_size = buffer_sizes.get(size_variable)

            # Case 2:
            # memcpy(buffer, input, 16);
            else:
                numeric_match = re.fullmatch(
                    r"\d+",
                    size_expression,
                )

                if numeric_match:
                    copy_size = int(numeric_match.group(0))

            if (
                copy_size is not None
                and copy_size > destination_size
            ):
                findings.append(
                    {
                        "type": "Potential buffer overflow",
                        "function": function_name,
                        "line": line_number,
                        "code": line.strip(),
                        "severity": "High",
                    }
                )

    return {
        "success": True,
        "source_file": str(source),
        "findings": findings,
        "error": None,
    }