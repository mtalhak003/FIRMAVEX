from pathlib import Path

from src.codepulse.analyzer.analyzer import analyze_firmware
from src.codepulse.compiler.compiler import compile_firmware


def analyze_and_compile(source_file: str, output_file: str) -> dict:
    """
    Analyze and compile a firmware source file.

    Returns the combined analysis and compilation results.
    """

    source = Path(source_file)

    analysis_result = analyze_firmware(str(source))

    if not analysis_result["success"]:
        return {
            "success": False,
            "source_file": str(source),
            "analysis": analysis_result,
            "compilation": None,
            "error": analysis_result["error"],
        }

    compilation_result = compile_firmware(
        str(source),
        output_file,
    )

    return {
        "success": compilation_result["success"],
        "source_file": str(source),
        "analysis": analysis_result,
        "compilation": compilation_result,
        "error": None if compilation_result["success"] else compilation_result["stderr"],
    }