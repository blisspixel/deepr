"""Offline parser and form-only conformance checks for OKF 0.2.

OKF 0.2 intentionally publishes a Markdown and YAML specification, not a
JSON Schema. This module implements only its mechanical bundle rules. It does
not judge the truth, quality, trust tier, or meaning of a concept.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from yaml.events import MappingEndEvent, MappingStartEvent, SequenceEndEvent, SequenceStartEvent

OKF_VERSION = "0.2"
OKF_RESERVED_FILENAMES = frozenset({"index.md", "log.md"})

_DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,}).*$")
_MAX_FRONTMATTER_CHARS = 256 * 1024
_MAX_YAML_EVENTS = 10_000
_MAX_YAML_DEPTH = 64
OKF_MAX_MARKDOWN_FILES = 10_000
OKF_MAX_MARKDOWN_FILE_BYTES = 8 * 1024 * 1024
OKF_MAX_MARKDOWN_TOTAL_BYTES = 64 * 1024 * 1024
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


@dataclass(frozen=True)
class ParsedFrontmatter:
    """One Markdown frontmatter parse with errors kept at the boundary."""

    present: bool
    fields: dict[Any, Any]
    body: str
    error: str | None = None


@dataclass(frozen=True)
class OKFViolation:
    """One deterministic OKF form violation."""

    code: str
    path: str
    detail: str


@dataclass(frozen=True)
class OKFBundleValidation:
    """Offline validation result for one bundle or concept document."""

    files: tuple[str, ...]
    violations: tuple[OKFViolation, ...]
    declared_version: str | None

    @property
    def valid(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class OKFMarkdownBundleRead:
    """One bounded, reusable read of an OKF Markdown bundle."""

    root: Path | None
    files: tuple[str, ...]
    documents: tuple[tuple[str, str], ...]
    violations: tuple[OKFViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def _bounded_yaml_tree(
    value: Any,
    *,
    active: frozenset[int] = frozenset(),
    depth: int = 0,
    node_count: list[int] | None = None,
) -> Any:
    node_count = [0] if node_count is None else node_count
    node_count[0] += 1
    if node_count[0] > _MAX_YAML_EVENTS:
        raise ValueError(f"frontmatter expands beyond {_MAX_YAML_EVENTS} YAML nodes")
    if depth > _MAX_YAML_DEPTH:
        raise ValueError(f"frontmatter exceeds YAML nesting depth {_MAX_YAML_DEPTH}")
    if isinstance(value, (tuple, set, frozenset)):
        raise ValueError(f"frontmatter uses unsupported YAML container {type(value).__name__}")
    if not isinstance(value, (dict, list)):
        return value
    identity = id(value)
    if identity in active:
        raise ValueError("cyclic YAML aliases are not accepted")
    descendants = active | {identity}
    if isinstance(value, list):
        return [_bounded_yaml_tree(item, active=descendants, depth=depth + 1, node_count=node_count) for item in value]
    return {
        key: _bounded_yaml_tree(item, active=descendants, depth=depth + 1, node_count=node_count)
        for key, item in value.items()
    }


def _load_bounded_yaml_mapping(raw_frontmatter: str) -> tuple[dict[Any, Any], str | None]:
    try:
        depth = 0
        for event_count, event in enumerate(yaml.parse(raw_frontmatter), start=1):
            if event_count > _MAX_YAML_EVENTS:
                raise ValueError(f"frontmatter exceeds {_MAX_YAML_EVENTS} YAML events")
            if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
                depth += 1
                if depth > _MAX_YAML_DEPTH:
                    raise ValueError(f"frontmatter exceeds YAML nesting depth {_MAX_YAML_DEPTH}")
            elif isinstance(event, (MappingEndEvent, SequenceEndEvent)):
                depth -= 1
        parsed = _bounded_yaml_tree(yaml.safe_load(raw_frontmatter))
    except (OverflowError, ValueError, yaml.YAMLError) as exc:
        return {}, f"invalid YAML: {exc}"
    if parsed is None:
        return {}, None
    if not isinstance(parsed, dict):
        return {}, "frontmatter must be a YAML mapping"
    return parsed, None


def parse_markdown_frontmatter(text: str, *, allow_leading_comments: bool = False) -> ParsedFrontmatter:
    """Parse YAML frontmatter without executing custom YAML tags.

    OKF concept frontmatter must start on the first line. The compatibility
    option exists only for reading Deepr's older generated views, which placed
    derived-view comments before the delimiter.
    """
    lines = text.splitlines()
    start = 0
    if allow_leading_comments:
        while start < len(lines):
            stripped = lines[start].strip()
            if not stripped or (stripped.startswith("<!--") and stripped.endswith("-->")):
                start += 1
                continue
            break

    if start >= len(lines) or lines[start].strip() != "---":
        return ParsedFrontmatter(present=False, fields={}, body=text)

    end = start + 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1
    if end >= len(lines):
        return ParsedFrontmatter(
            present=True,
            fields={},
            body="",
            error="frontmatter has no closing --- delimiter",
        )

    raw_frontmatter = "\n".join(lines[start + 1 : end])
    if len(raw_frontmatter) > _MAX_FRONTMATTER_CHARS:
        return ParsedFrontmatter(
            present=True,
            fields={},
            body="",
            error=f"frontmatter exceeds {_MAX_FRONTMATTER_CHARS} characters",
        )
    fields, error = _load_bounded_yaml_mapping(raw_frontmatter)
    if error:
        return ParsedFrontmatter(present=True, fields={}, body="", error=error)
    return ParsedFrontmatter(
        present=True,
        fields=fields,
        body="\n".join(lines[end + 1 :]).strip(),
    )


def _markdown_files(path: Path) -> tuple[Path, list[Path], OKFViolation | None]:
    resolved = path.resolve(strict=True)
    if resolved.is_file():
        return resolved.parent, [resolved], None

    markdown_files: list[Path] = []
    for candidate in resolved.rglob("*.md"):
        if len(markdown_files) >= OKF_MAX_MARKDOWN_FILES:
            violation = OKFViolation(
                code="markdown_file_count_limit",
                path=resolved.as_posix(),
                detail=f"Bundle exceeds the maximum of {OKF_MAX_MARKDOWN_FILES} Markdown files",
            )
            return resolved, [], violation
        markdown_files.append(candidate)
    return resolved, sorted(markdown_files), None


def _relative_file(root: Path, candidate: Path) -> tuple[str | None, OKFViolation | None]:
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        return None, OKFViolation(
            code="path_outside_bundle",
            path=candidate.as_posix(),
            detail=f"Markdown path does not resolve inside the bundle: {exc}",
        )
    return relative, None


def _preflight_markdown_files(
    root: Path,
    markdown_files: list[Path],
) -> tuple[list[str], list[tuple[str, Path]], list[OKFViolation]]:
    files: list[str] = []
    preflight: list[tuple[str, Path]] = []
    violations: list[OKFViolation] = []
    total_bytes = 0
    for markdown_file in markdown_files:
        relative_path, path_violation = _relative_file(root, markdown_file)
        if path_violation is not None:
            violations.append(path_violation)
            continue
        if relative_path is None:
            violations.append(
                OKFViolation(
                    "path_unreadable",
                    markdown_file.as_posix(),
                    "Markdown path could not be resolved relative to the bundle",
                )
            )
            continue
        files.append(relative_path)
        try:
            file_bytes = markdown_file.stat().st_size
        except OSError as exc:
            violations.append(OKFViolation("path_unreadable", relative_path, str(exc)))
            continue
        if file_bytes > OKF_MAX_MARKDOWN_FILE_BYTES:
            violations.append(
                OKFViolation(
                    "markdown_file_size_limit",
                    relative_path,
                    f"File exceeds the maximum of {OKF_MAX_MARKDOWN_FILE_BYTES} bytes",
                )
            )
        total_bytes += file_bytes
        preflight.append((relative_path, markdown_file))

    if total_bytes > OKF_MAX_MARKDOWN_TOTAL_BYTES:
        violations.append(
            OKFViolation(
                "markdown_total_size_limit",
                root.as_posix(),
                f"Bundle exceeds the maximum of {OKF_MAX_MARKDOWN_TOTAL_BYTES} Markdown bytes",
            )
        )
    return files, preflight, violations


def _read_markdown_files(
    root: Path,
    preflight: list[tuple[str, Path]],
) -> tuple[list[tuple[str, str]], list[OKFViolation]]:
    documents: list[tuple[str, str]] = []
    violations: list[OKFViolation] = []
    actual_total_bytes = 0
    for relative_path, markdown_file in preflight:
        aggregate_remaining = OKF_MAX_MARKDOWN_TOTAL_BYTES - actual_total_bytes
        read_limit = min(OKF_MAX_MARKDOWN_FILE_BYTES, aggregate_remaining)
        try:
            with markdown_file.open("rb") as handle:
                raw = handle.read(read_limit + 1)
        except OSError as exc:
            violations.append(OKFViolation("utf8_read", relative_path, str(exc)))
            break
        if len(raw) > read_limit:
            if aggregate_remaining < OKF_MAX_MARKDOWN_FILE_BYTES:
                violation = OKFViolation(
                    "markdown_total_size_limit",
                    root.as_posix(),
                    f"Bundle exceeds the maximum of {OKF_MAX_MARKDOWN_TOTAL_BYTES} Markdown bytes",
                )
            else:
                violation = OKFViolation(
                    "markdown_file_size_limit",
                    relative_path,
                    f"File exceeds the maximum of {OKF_MAX_MARKDOWN_FILE_BYTES} bytes",
                )
            violations.append(violation)
            break
        actual_total_bytes += len(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            violations.append(OKFViolation("utf8_read", relative_path, str(exc)))
            break
        documents.append((relative_path, text))
    return documents, violations


def read_bounded_markdown_bundle(path: Path) -> OKFMarkdownBundleRead:
    """Enumerate, preflight, and read one Markdown bundle within fixed limits."""
    try:
        root, markdown_files, enumeration_violation = _markdown_files(path)
    except (OSError, RuntimeError, ValueError) as exc:
        violation = OKFViolation("path_unreadable", path.as_posix(), str(exc))
        return OKFMarkdownBundleRead(None, (), (), (violation,))
    if enumeration_violation is not None:
        return OKFMarkdownBundleRead(root, (), (), (enumeration_violation,))

    files, preflight, violations = _preflight_markdown_files(root, markdown_files)
    if violations:
        return OKFMarkdownBundleRead(root, tuple(files), (), tuple(violations))
    documents, violations = _read_markdown_files(root, preflight)
    if violations:
        return OKFMarkdownBundleRead(root, tuple(files), (), tuple(violations))
    return OKFMarkdownBundleRead(root, tuple(files), tuple(documents), ())


def _validate_index(
    relative_path: str,
    text: str,
    parsed: ParsedFrontmatter,
    *,
    expected_version: str,
) -> tuple[list[OKFViolation], str | None]:
    violations: list[OKFViolation] = []
    if parsed.error:
        violations.append(OKFViolation("invalid_reserved_frontmatter", relative_path, parsed.error))
        return violations, None
    if relative_path != "index.md" and parsed.present:
        violations.append(
            OKFViolation(
                "nested_index_frontmatter",
                relative_path,
                "Only the bundle-root index.md may contain frontmatter",
            )
        )
        return violations, None
    if not parsed.present:
        compatibility_parse = parse_markdown_frontmatter(text, allow_leading_comments=True)
        if compatibility_parse.present:
            violations.append(
                OKFViolation(
                    "index_frontmatter_position",
                    relative_path,
                    "Root index.md frontmatter must start on the first line",
                )
            )
        return violations, None

    unknown = sorted(str(key) for key in parsed.fields if key != "okf_version")
    if unknown:
        violations.append(
            OKFViolation(
                "root_index_frontmatter_keys",
                relative_path,
                f"Root index.md frontmatter may contain only okf_version; found: {', '.join(unknown)}",
            )
        )
    raw_version = parsed.fields.get("okf_version")
    declared_version = raw_version if isinstance(raw_version, str) else None
    if declared_version != expected_version:
        violations.append(
            OKFViolation(
                "okf_version",
                relative_path,
                f"Expected okf_version {expected_version!r}, found {declared_version or '(missing)'!r}",
            )
        )
    return violations, declared_version


def _markdown_h2_lines(text: str) -> list[str]:
    headings: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in text.splitlines():
        if fence_character:
            stripped = line.lstrip(" ")
            if (
                len(line) - len(stripped) <= 3
                and stripped.startswith(fence_character * fence_length)
                and not stripped.rstrip().strip(fence_character)
            ):
                fence_character = ""
                fence_length = 0
            continue
        if fence := _FENCE_RE.fullmatch(line):
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue
        stripped = line.lstrip(" ")
        if len(line) - len(stripped) <= 3 and stripped.startswith("## "):
            headings.append(stripped)
    return headings


def _validate_log(relative_path: str, text: str, parsed: ParsedFrontmatter) -> list[OKFViolation]:
    violations: list[OKFViolation] = []
    if parsed.present:
        detail = parsed.error or "log.md must not contain frontmatter"
        violations.append(OKFViolation("log_frontmatter", relative_path, detail))

    headings: list[str] = []
    for heading in _markdown_h2_lines(text):
        match = _DATE_HEADING_RE.fullmatch(heading)
        if match is None:
            violations.append(
                OKFViolation(
                    "log_date_heading",
                    relative_path,
                    f"Log level-two heading must use YYYY-MM-DD: {heading}",
                )
            )
        else:
            heading_date = match.group(1)
            try:
                date.fromisoformat(heading_date)
            except ValueError:
                violations.append(
                    OKFViolation(
                        "log_date_heading",
                        relative_path,
                        f"Log level-two heading is not a calendar date: {heading_date}",
                    )
                )
            else:
                headings.append(heading_date)
    if headings != sorted(headings, reverse=True):
        violations.append(
            OKFViolation(
                "log_date_order",
                relative_path,
                "Log date headings must be newest first",
            )
        )
    return violations


def _validate_concept(relative_path: str, parsed: ParsedFrontmatter) -> list[OKFViolation]:
    if not parsed.present:
        return [
            OKFViolation(
                "concept_frontmatter",
                relative_path,
                "Concept frontmatter must begin on the first line",
            )
        ]
    if parsed.error:
        return [OKFViolation("concept_frontmatter", relative_path, parsed.error)]
    concept_type = parsed.fields.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        return [
            OKFViolation(
                "concept_type",
                relative_path,
                "Concept frontmatter requires a non-empty string type",
            )
        ]
    return []


def portable_relative_path_failure(normalized: str) -> str | None:
    """Return why a normalized bundle path is not portable, if applicable."""
    raw_parts = normalized.split("/")
    if not normalized or normalized.endswith("/") or any(part in {"", ".", ".."} for part in raw_parts):
        return "Document path must name a file without empty, dot, or parent segments"
    if any(any(ord(character) < 32 or ord(character) == 127 for character in part) for part in raw_parts):
        return "Document path must not contain control characters"
    if any(":" in part or part.endswith((" ", ".")) for part in raw_parts):
        return "Document path must not contain ADS separators or trailing spaces or dots"
    for part in raw_parts:
        device_stem = part.rstrip(" .").split(".", 1)[0].upper()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            return f"Document path uses reserved Windows device name {device_stem}"
    windows_path = PureWindowsPath(normalized)
    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        return "Document path must be relative and remain inside the bundle"
    return None


def validate_okf_documents(
    documents: Mapping[str, str],
    *,
    expected_version: str = OKF_VERSION,
) -> OKFBundleValidation:
    """Validate an in-memory bundle before any generated file is written."""
    files: list[str] = []
    violations: list[OKFViolation] = []
    declared_version: str | None = None
    normalized_paths: dict[str, str] = {}
    for raw_path, text in sorted(documents.items()):
        normalized = str(raw_path).replace("\\", "/")
        pure_path = PurePosixPath(normalized)
        if path_failure := portable_relative_path_failure(normalized):
            violations.append(
                OKFViolation(
                    "path_outside_bundle",
                    normalized,
                    path_failure,
                )
            )
            continue
        relative_path = pure_path.as_posix()
        collision_key = relative_path.casefold()
        if previous := normalized_paths.get(collision_key):
            violations.append(
                OKFViolation(
                    "path_collision",
                    relative_path,
                    f"Document path collides with {previous!r} after portable normalization",
                )
            )
            continue
        normalized_paths[collision_key] = relative_path
        if pure_path.suffix.lower() != ".md":
            continue
        files.append(relative_path)
        parsed = parse_markdown_frontmatter(text)
        if pure_path.name == "index.md":
            index_violations, index_version = _validate_index(
                relative_path,
                text,
                parsed,
                expected_version=expected_version,
            )
            violations.extend(index_violations)
            if relative_path == "index.md" and index_version is not None:
                declared_version = index_version
        elif pure_path.name == "log.md":
            violations.extend(_validate_log(relative_path, text, parsed))
        else:
            violations.extend(_validate_concept(relative_path, parsed))

    return OKFBundleValidation(
        files=tuple(files),
        violations=tuple(violations),
        declared_version=declared_version,
    )


def validate_okf_bundle(path: Path, *, expected_version: str = OKF_VERSION) -> OKFBundleValidation:
    """Validate the hard OKF 0.2 bundle rules without model or network calls."""
    bundle_read = read_bounded_markdown_bundle(path)
    if bundle_read.violations:
        return OKFBundleValidation(
            files=bundle_read.files,
            violations=bundle_read.violations,
            declared_version=None,
        )

    content_result = validate_okf_documents(dict(bundle_read.documents), expected_version=expected_version)

    return OKFBundleValidation(
        files=bundle_read.files,
        violations=content_result.violations,
        declared_version=content_result.declared_version,
    )


__all__ = [
    "OKF_MAX_MARKDOWN_FILES",
    "OKF_MAX_MARKDOWN_FILE_BYTES",
    "OKF_MAX_MARKDOWN_TOTAL_BYTES",
    "OKF_VERSION",
    "OKFBundleValidation",
    "OKFMarkdownBundleRead",
    "OKFViolation",
    "ParsedFrontmatter",
    "parse_markdown_frontmatter",
    "portable_relative_path_failure",
    "read_bounded_markdown_bundle",
    "validate_okf_bundle",
    "validate_okf_documents",
]
