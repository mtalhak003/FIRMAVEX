from pathlib import Path
import re


DANGEROUS_FUNCTIONS = {
    "strcpy": "Potential buffer overflow",
    "strcat": "Potential buffer overflow",
    "gets": "Potential buffer overflow",
    "sprintf": "Potential buffer overflow",
}


def remove_comments_and_strings(line: str) -> str:
    """
    Remove comments and string literals from one line of C code.

    This prevents the analyzer from detecting dangerous functions
    inside comments or printed text.
    """

    # Remove single-line comments.
    line = line.split("//", 1)[0]

    # Remove C string literals.
    line = re.sub(r'"(?:\\.|[^"\\])*"', "", line)

    return line


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

    findings = []

    for line_number, line in enumerate(source_code.splitlines(), start=1):
        stripped_line = line.strip()

        # Ignore single-line comments.
        if stripped_line.startswith("//"):
            continue

        code_line = remove_comments_and_strings(line)

        for function_name, description in DANGEROUS_FUNCTIONS.items():
            pattern = rf"\b{re.escape(function_name)}\s*\("

            if re.search(pattern, code_line):
                findings.append(
                    {
                        "type": description,
                        "function": function_name,
                        "line": line_number,
                        "code": code_line.strip(),
                        "severity": "High",
                    }
                )

    return {
        "success": True,
        "source_file": str(source),
        "findings": findings,
        "error": None,
    }