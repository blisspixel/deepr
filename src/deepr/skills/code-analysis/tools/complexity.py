"""Cyclomatic complexity analysis."""

from __future__ import annotations

import re
from typing import Any


def complexity_report(code: str, language: str = "auto") -> dict[str, Any]:
    """Calculate cyclomatic complexity and code metrics.

    Args:
        code: Source code to analyze
        language: Programming language

    Returns:
        Per-function complexity and overall assessment
    """
    if language == "auto":
        language = "python" if ("def " in code or "class " in code) else "javascript"

    lines = code.split("\n")
    total_lines = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    comment_lines = sum(1 for line in lines if line.strip().startswith(("#", "//", "/*", "*")))

    if language == "python":
        functions = _analyze_python_functions(code)
    else:
        functions = _analyze_js_functions(code)

    complexities = [f["complexity"] for f in functions] if functions else [1]
    avg = sum(complexities) / len(complexities)
    max_c = max(complexities)

    if max_c <= 5:
        assessment = "low"
    elif max_c <= 10:
        assessment = "moderate"
    elif max_c <= 20:
        assessment = "high"
    else:
        assessment = "very_high"

    return {
        "language": language,
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "code_lines": total_lines - blank_lines - comment_lines,
        "functions": functions,
        "function_count": len(functions),
        "avg_complexity": round(avg, 1),
        "max_complexity": max_c,
        "assessment": assessment,
    }


def _analyze_python_functions(code: str) -> list[dict[str, Any]]:
    functions = []
    # Match function definitions
    for match in re.finditer(r"^(\s*)def\s+(\w+)\s*\(", code, re.MULTILINE):
        indent = len(match.group(1))
        name = match.group(2)
        start = match.start()

        # Find function body (lines with greater indent)
        body_lines = []
        in_body = False
        for line in code[start:].split("\n")[1:]:
            stripped = line.rstrip()
            if not stripped:
                body_lines.append(stripped)
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent > indent:
                in_body = True
                body_lines.append(stripped)
            elif in_body and line_indent <= indent and stripped:
                break

        body = "\n".join(body_lines)
        complexity = _calculate_complexity(body)
        functions.append(
            {
                "name": name,
                "line": code[:start].count("\n") + 1,
                "complexity": complexity,
                "body_lines": len([line for line in body_lines if line.strip()]),
            }
        )

    return functions


def _analyze_js_functions(code: str) -> list[dict[str, Any]]:
    functions = []
    for match in re.finditer(
        r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))", code
    ):
        name = match.group(1) or match.group(2)
        start = match.start()
        # Simple brace counting for body
        brace_start = code.find("{", start)
        if brace_start == -1:
            continue
        depth = 0
        end = brace_start
        for i in range(brace_start, len(code)):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        body = code[brace_start:end]
        complexity = _calculate_complexity(body)
        functions.append(
            {
                "name": name,
                "line": code[:start].count("\n") + 1,
                "complexity": complexity,
            }
        )

    return functions


def _calculate_complexity(body: str) -> int:
    """Calculate cyclomatic complexity of a code block."""
    complexity = 1  # Base complexity
    # Decision points
    decision_patterns = [
        r"\bif\b",
        r"\belif\b",
        r"\belse\b",
        r"\bfor\b",
        r"\bwhile\b",
        r"\band\b",
        r"\bor\b",
        r"\bcatch\b",
        r"\bexcept\b",
        r"\bcase\b",
        r"\?\s*",  # ternary
        r"&&",
        r"\|\|",
    ]
    for pattern in decision_patterns:
        complexity += len(re.findall(pattern, body))
    return complexity
