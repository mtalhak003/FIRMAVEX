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

    findings = []

    for line_number, line in enumerate(
        cleaned_code.splitlines(),
        start=1,
    ):
        # Check dangerous functions such as strcpy().
        for function_name, description in DANGEROUS_FUNCTIONS.items():
            pattern = rf"\b{re.escape(function_name)}\s*\("

            if re.search(pattern, line):
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
