"""Prompt security utilities for injection detection and sanitization.

Provides protection against prompt injection attacks and malicious inputs.
Implements defense-in-depth with multiple sanitization layers.

Requirements: 8.1 - Implement injection pattern detection and sanitization
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SanitizationResult:
    """Result of prompt sanitization."""

    original: str
    sanitized: str
    patterns_detected: list[str]
    was_modified: bool
    risk_level: str  # "low", "medium", "high"

    @property
    def is_safe(self) -> bool:
        """Check if the prompt is considered safe after sanitization."""
        return self.risk_level in ("low", "medium")


class PromptSanitizer:
    """Sanitizes prompts to prevent injection attacks.

    Detects and neutralizes common prompt injection patterns while
    preserving legitimate research queries.

    Example:
        sanitizer = PromptSanitizer()
        result = sanitizer.sanitize("Ignore previous instructions and...")
        if not result.is_safe:
            raise ValueError("Potentially malicious prompt detected")
    """

    # Patterns that indicate potential prompt injection
    # Each tuple: (pattern, description, risk_level)
    INJECTION_PATTERNS: list[tuple[str, str, str]] = [
        # Direct instruction override attempts
        (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", "instruction_override", "high"),
        (r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", "instruction_override", "high"),
        (r"forget\s+(everything|all)\s+(you\s+)?(know|learned|were\s+told)", "instruction_override", "high"),
        # System prompt extraction attempts
        (
            r"(show|reveal|display|print|output)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?)",
            "system_extraction",
            "high",
        ),
        (r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)", "system_extraction", "medium"),
        (r"repeat\s+(your\s+)?(initial|original|system)\s+(prompt|instructions?)", "system_extraction", "high"),
        # Role manipulation attempts
        (r"you\s+are\s+now\s+(a|an)\s+\w+", "role_manipulation", "medium"),
        (r"pretend\s+(to\s+be|you\s+are)\s+(a|an)\s+\w+", "role_manipulation", "medium"),
        (r"act\s+as\s+(if\s+you\s+are\s+)?(a|an)\s+\w+", "role_manipulation", "low"),  # Common legitimate use
        # Jailbreak attempts
        (r"(DAN|do\s+anything\s+now)\s+mode", "jailbreak", "high"),
        (r"developer\s+mode\s+(enabled|on|activated)", "jailbreak", "high"),
        (r"bypass\s+(safety|content|ethical)\s+(filters?|restrictions?|guidelines?)", "jailbreak", "high"),
        # Code execution attempts (for research context)
        (r"execute\s+(this\s+)?(code|script|command)", "code_execution", "medium"),
        (r"run\s+(this\s+)?(python|bash|shell|code)", "code_execution", "medium"),
        # Data exfiltration attempts
        (r"(send|transmit|upload)\s+(to|data\s+to)\s+https?://", "data_exfiltration", "high"),
        (r"curl\s+.*https?://", "data_exfiltration", "high"),
    ]

    # Patterns to neutralize (replace with safe alternatives)
    NEUTRALIZATION_PATTERNS: list[tuple[str, str]] = [
        # Neutralize instruction overrides
        (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", "[instruction reference removed]"),
        (r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", "[instruction reference removed]"),
        # Neutralize system prompt extraction
        (r"(show|reveal|display|print)\s+(your\s+)?(system\s+)?prompt", "[prompt request removed]"),
        # Neutralize jailbreak keywords
        (r"\bDAN\s+mode\b", "[mode reference removed]"),
        (r"developer\s+mode", "[mode reference removed]"),
    ]

    def __init__(self, strict_mode: bool = False):
        """Initialize sanitizer.

        Args:
            strict_mode: If True, reject any prompt with detected patterns.
                        If False, attempt to neutralize and continue.
        """
        self.strict_mode = strict_mode
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), desc, risk) for pattern, desc, risk in self.INJECTION_PATTERNS
        ]
        self._compiled_neutralizers = [
            (re.compile(pattern, re.IGNORECASE), replacement) for pattern, replacement in self.NEUTRALIZATION_PATTERNS
        ]

    def detect_patterns(self, text: str) -> list[tuple[str, str]]:
        """Detect injection patterns in text.

        Args:
            text: Text to analyze

        Returns:
            List of (pattern_description, risk_level) tuples
        """
        detected = []
        for pattern, description, risk in self._compiled_patterns:
            if pattern.search(text):
                detected.append((description, risk))
        return detected

    def calculate_risk_level(self, detected_patterns: list[tuple[str, str]]) -> str:
        """Calculate overall risk level from detected patterns.

        Args:
            detected_patterns: List of (description, risk) tuples

        Returns:
            Overall risk level: "low", "medium", or "high"
        """
        if not detected_patterns:
            return "low"

        risk_levels = [risk for _, risk in detected_patterns]

        if "high" in risk_levels:
            return "high"
        elif "medium" in risk_levels:
            return "medium"
        else:
            return "low"

    def neutralize(self, text: str) -> str:
        """Neutralize detected injection patterns.

        Args:
            text: Text to neutralize

        Returns:
            Neutralized text with dangerous patterns replaced
        """
        result = text
        for pattern, replacement in self._compiled_neutralizers:
            result = pattern.sub(replacement, result)
        return result

    def sanitize(self, prompt: str) -> SanitizationResult:
        """Sanitize a prompt for safe use.

        Args:
            prompt: User-provided prompt

        Returns:
            SanitizationResult with sanitization details
        """
        # Detect patterns
        detected = self.detect_patterns(prompt)
        pattern_descriptions = [desc for desc, _ in detected]
        risk_level = self.calculate_risk_level(detected)

        # In strict mode, don't modify - just report
        if self.strict_mode:
            return SanitizationResult(
                original=prompt,
                sanitized=prompt,
                patterns_detected=pattern_descriptions,
                was_modified=False,
                risk_level=risk_level,
            )

        # Neutralize dangerous patterns
        sanitized = self.neutralize(prompt)
        was_modified = sanitized != prompt

        return SanitizationResult(
            original=prompt,
            sanitized=sanitized,
            patterns_detected=pattern_descriptions,
            was_modified=was_modified,
            risk_level=risk_level,
        )

    def validate(self, prompt: str) -> tuple[bool, Optional[str]]:
        """Validate a prompt and return simple pass/fail.

        Args:
            prompt: Prompt to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        result = self.sanitize(prompt)

        if result.risk_level == "high":
            return False, f"High-risk patterns detected: {', '.join(result.patterns_detected)}"

        return True, None


def sanitize_prompt(prompt: str, strict: bool = False) -> str:
    """Convenience function to sanitize a prompt.

    Args:
        prompt: Prompt to sanitize
        strict: If True, raise on high-risk patterns

    Returns:
        Sanitized prompt

    Raises:
        ValueError: If strict=True and high-risk patterns detected
    """
    sanitizer = PromptSanitizer(strict_mode=strict)
    result = sanitizer.sanitize(prompt)

    if strict and result.risk_level == "high":
        raise ValueError(f"Prompt contains high-risk patterns: {result.patterns_detected}")

    return result.sanitized


def validate_prompt(prompt: str) -> tuple[bool, Optional[str]]:
    """Convenience function to validate a prompt.

    Args:
        prompt: Prompt to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    sanitizer = PromptSanitizer()
    return sanitizer.validate(prompt)
