from pathlib import Path
import re


DANGEROUS_FUNCTIONS = {
    "strcpy": "Potential buffer overflow",
    "strcat": "Potential buffer overflow",
    "gets": "Potential buffer overflow",
    "sprintf": "Potential buffer overflow",
}


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

    return {
        "success": True,
        "source_file": str(source),
        "findings": findings,
        "error": None,
    }