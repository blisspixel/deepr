"""Security utilities for Deepr."""

import ipaddress
import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# A safe path segment is either a slug (letters, digits, ``-``, ``_`` with no
# leading/trailing separator) or a canonical UUID. This deliberately rejects
# path separators, "..", null bytes, whitespace, and any other token that could
# be used to traverse out of an intended directory.
_SLUG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class SecurityError(Exception):
    """Base exception for security violations."""

    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal is detected."""

    pass


class SSRFError(SecurityError):
    """Raised when SSRF (Server-Side Request Forgery) is detected."""

    pass


class InvalidInputError(SecurityError):
    """Raised when input validation fails."""

    pass


def sanitize_name(name: str, allowed_chars: str = r"a-zA-Z0-9_-", raise_on_change: bool = False) -> str:
    """
    Sanitize a name by removing dangerous characters.

    Args:
        name: The name to sanitize
        allowed_chars: Regex character class of allowed characters
        raise_on_change: When True, raise ``InvalidInputError`` if the
            input contained characters that had to be replaced. Use this
            from path-construction sites that want to reject
            ``../../passwd``-style inputs outright instead of silently
            sanitising them into a benign-looking name.

    Returns:
        Sanitized name

    Examples:
        >>> sanitize_name("my expert")
        'my_expert'
        >>> sanitize_name("../../etc/passwd")
        'etc_passwd'
        >>> sanitize_name("../../etc/passwd", raise_on_change=True)
        Traceback (most recent call last):
            ...
        deepr.utils.security.InvalidInputError: ...
    """
    pattern = f"[^{allowed_chars}]"
    sanitized = re.sub(pattern, "_", name)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Ensure not empty
    if not sanitized:
        raise InvalidInputError("Name cannot be empty after sanitization")

    if raise_on_change and sanitized != name:
        raise InvalidInputError(
            f"Name {name!r} contains characters that are not permitted (allowed: [{allowed_chars}])"
        )

    return sanitized


def validate_path(
    user_path: str | Path, base_dir: str | Path, must_exist: bool = False, allow_create: bool = True
) -> Path:
    """
    Validate that a user-provided path is safe and within allowed directory.

    Args:
        user_path: User-provided path
        base_dir: Base directory that path must be within
        must_exist: If True, path must already exist
        allow_create: If True, allow paths that don't exist yet

    Returns:
        Resolved, validated Path object

    Raises:
        PathTraversalError: If path escapes base directory
        FileNotFoundError: If must_exist=True and path doesn't exist
        InvalidInputError: If path is invalid

    Examples:
        >>> base = Path("/app/data")
        >>> validate_path("experts/my_expert", base)
        PosixPath('/app/data/experts/my_expert')
        >>> validate_path("../../etc/passwd", base)  # Raises PathTraversalError
    """
    if not user_path:
        raise InvalidInputError("Path cannot be empty")

    base = Path(base_dir).resolve()
    path = Path(user_path)

    # Handle absolute paths
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (base / path).resolve()

    # Check if path is within base directory
    try:
        resolved.relative_to(base)
    except ValueError as err:
        raise PathTraversalError(f"Path '{user_path}' attempts to escape base directory '{base}'") from err

    # Check existence requirements
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    if not allow_create and not resolved.exists():
        raise InvalidInputError(f"Path creation not allowed: {resolved}")

    return resolved


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool = False) -> bool:
    """Check if an IP address should be blocked.

    Handles both IPv4 and IPv6 addresses.
    """
    if ip.is_reserved or ip.is_multicast:
        return True
    if not allow_private:
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def resolve_all_ips(hostname: str) -> list[str]:
    """Resolve hostname to all IP addresses (IPv4 and IPv6).

    Uses getaddrinfo instead of gethostbyname to support IPv6.
    """
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return list({result[4][0] for result in results})
    except socket.gaierror:
        return []


def is_safe_url(url: str, allow_private: bool = False) -> bool:
    """
    Check if a URL is safe to fetch (SSRF protection).

    Resolves both IPv4 and IPv6 addresses and blocks private/internal ranges.

    Args:
        url: URL to validate
        allow_private: If True, allow private IP ranges

    Returns:
        True if URL is safe, False otherwise

    Examples:
        >>> is_safe_url("https://example.com")
        True
        >>> is_safe_url("http://localhost:8000")
        False
        >>> is_safe_url("http://192.168.1.1")
        False
        >>> is_safe_url("file:///etc/passwd")
        False
    """
    try:
        parsed = urlparse(url)

        # Only allow HTTP(S)
        if parsed.scheme not in ["http", "https"]:
            return False

        # Check for hostname
        if not parsed.hostname:
            return False

        # Resolve hostname to all IPs (IPv4 + IPv6) and check each
        ip_strings = resolve_all_ips(parsed.hostname)
        if not ip_strings:
            # DNS resolution failed -- be conservative and block
            return False

        for ip_str in ip_strings:
            try:
                ip = ipaddress.ip_address(ip_str)
                if is_blocked_ip(ip, allow_private):
                    return False
            except ValueError:
                return False

        return True

    except Exception:
        return False


def validate_url(url: str, allow_private: bool = False) -> str:
    """
    Validate URL and raise exception if unsafe.

    Args:
        url: URL to validate
        allow_private: If True, allow private IP ranges

    Returns:
        The validated URL

    Raises:
        SSRFError: If URL is potentially dangerous

    Examples:
        >>> validate_url("https://example.com")
        'https://example.com'
        >>> validate_url("http://localhost")  # Raises SSRFError
    """
    if not is_safe_url(url, allow_private=allow_private):
        raise SSRFError(f"URL is not safe to fetch: {url}")
    return url


def validate_file_size(file_path: str | Path, max_size_mb: int = 100) -> Path:
    """
    Validate file size is within limits.

    Args:
        file_path: Path to file
        max_size_mb: Maximum file size in megabytes

    Returns:
        Path object if valid

    Raises:
        InvalidInputError: If file is too large
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> validate_file_size("small.pdf", max_size_mb=10)
        PosixPath('small.pdf')
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    size_mb = path.stat().st_size / (1024 * 1024)

    if size_mb > max_size_mb:
        raise InvalidInputError(f"File size ({size_mb:.2f} MB) exceeds limit ({max_size_mb} MB): {path}")

    return path


def validate_file_extension(file_path: str | Path, allowed_extensions: list[str]) -> Path:
    """
    Validate file extension is in allowed list.

    Args:
        file_path: Path to file
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.txt'])

    Returns:
        Path object if valid

    Raises:
        InvalidInputError: If extension not allowed

    Examples:
        >>> validate_file_extension("doc.pdf", ['.pdf', '.txt'])
        PosixPath('doc.pdf')
        >>> validate_file_extension("script.exe", ['.pdf', '.txt'])  # Raises
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in [e.lower() for e in allowed_extensions]:
        raise InvalidInputError(f"File extension '{ext}' not allowed. Allowed: {allowed_extensions}")

    return path


def validate_prompt_length(prompt: str, max_length: int = 50000) -> str:
    """
    Validate prompt length to prevent excessive token usage.

    Args:
        prompt: The prompt to validate
        max_length: Maximum prompt length in characters

    Returns:
        The validated prompt

    Raises:
        InvalidInputError: If prompt is too long

    Examples:
        >>> validate_prompt_length("short prompt")
        'short prompt'
        >>> validate_prompt_length("x" * 100000)  # Raises InvalidInputError
    """
    if len(prompt) > max_length:
        raise InvalidInputError(f"Prompt length ({len(prompt)}) exceeds limit ({max_length})")

    return prompt


def validate_api_key(api_key: str, provider: str) -> str:
    """
    Validate API key format.

    Args:
        api_key: The API key to validate
        provider: Provider name ('openai', 'gemini', 'xai', 'azure', 'anthropic')

    Returns:
        The validated API key

    Raises:
        InvalidInputError: If API key format is invalid

    Examples:
        >>> validate_api_key("sk-proj-abcd1234", "openai")
        'sk-proj-abcd1234'
    """
    if not api_key or not api_key.strip():
        raise InvalidInputError(f"API key for {provider} is empty")

    # Provider-specific validation
    patterns = {
        "openai": r"^sk-(proj-)?[A-Za-z0-9_-]{20,}$",
        "anthropic": r"^sk-ant-[A-Za-z0-9_-]{20,}$",
        "gemini": r"^[A-Za-z0-9_-]{20,}$",
        "xai": r"^xai-[A-Za-z0-9_-]{20,}$",
        "azure": r"^[A-Za-z0-9]{32,}$",  # Azure keys are typically 32 chars
    }

    pattern = patterns.get(provider.lower())
    if pattern and not re.match(pattern, api_key):
        raise InvalidInputError(f"API key for {provider} does not match expected format")

    return api_key


def sanitize_log_message(message: str) -> str:
    """
    Sanitize log message to remove sensitive information.

    Args:
        message: Log message to sanitize

    Returns:
        Sanitized log message

    Examples:
        >>> sanitize_log_message("API key: example-value")
        'API key: [REDACTED]'
    """
    # Patterns for sensitive data
    patterns = [
        (r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_-]+)', r"\1[REDACTED]"),
        (r'(password["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r"\1[REDACTED]"),
        (r'(token["\']?\s*[:=]\s*["\']?)([A-Za-z0-9_.-]+)', r"\1[REDACTED]"),
        (r"(sk-[a-z]+-[A-Za-z0-9_-]+)", r"[REDACTED]"),  # OpenAI keys
        (r"(xai-[A-Za-z0-9_-]+)", r"[REDACTED]"),  # xAI keys
    ]

    sanitized = message
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_identifier(value: str, *, kind: str = "identifier") -> str:
    """Validate a user-supplied identifier used as a single path segment.

    Intended for expert names, session ids, job ids, report ids and similar
    tokens that are later joined into a filesystem path. The value must be a
    slug (letters, digits, ``-``, ``_``, ``.`` - not leading/trailing) or a
    canonical UUID. Path separators, ``..``, null bytes, whitespace, absolute
    paths and empty values are rejected.

    Args:
        value: The raw identifier supplied by the caller or end user.
        kind: Label for the identifier kind, used only in error messages
            (for example "expert name" or "job id").

    Returns:
        The validated identifier, unchanged.

    Raises:
        ValueError: If the identifier is empty, not a string, or contains any
            token that is unsafe to use as a path segment.

    Examples:
        >>> validate_identifier("my-expert_1")
        'my-expert_1'
        >>> validate_identifier("123e4567-e89b-12d3-a456-426614174000")
        '123e4567-e89b-12d3-a456-426614174000'
        >>> validate_identifier("../etc")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        ValueError: ...
    """
    if not isinstance(value, str):
        raise ValueError(f"{kind} must be a string, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{kind} cannot be empty")
    if "\x00" in value:
        raise ValueError(f"{kind} contains a null byte")
    if "/" in value or "\\" in value:
        raise ValueError(f"{kind} {value!r} must not contain path separators")
    if value in (".", ".."):
        raise ValueError(f"{kind} {value!r} is a reserved path segment")
    if _UUID_RE.match(value):
        return value
    if not _SLUG_RE.match(value):
        raise ValueError(
            f"{kind} {value!r} is not a valid slug or UUID "
            "(allowed: letters, digits, '-', '_', '.' - not leading/trailing)"
        )
    return value


def safe_path_within(base: str | Path, *parts: str) -> Path:
    """Join ``parts`` under ``base`` and assert the result stays inside ``base``.

    Resolves both ``base`` and the joined path to their real (symlink-resolved)
    locations and verifies the result is contained within ``base``. This guards
    against traversal via ``..``, absolute path segments, and symlink escapes.

    Args:
        base: The directory the resulting path must stay inside.
        *parts: Path segments to join beneath ``base``.

    Returns:
        The resolved, validated path inside ``base``.

    Raises:
        ValueError: If the resolved path escapes ``base``, or if any segment is
            empty.

    Examples:
        >>> safe_path_within("/data", "experts", "alice").name
        'alice'
        >>> safe_path_within("/data", "..", "etc")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        ValueError: ...
    """
    base_path = Path(base)
    if not parts:
        raise ValueError("at least one path segment is required")
    for part in parts:
        if not isinstance(part, str) or not part:
            raise ValueError("path segments must be non-empty strings")

    try:
        base_real = base_path.resolve(strict=False)
        candidate = base_path.joinpath(*parts).resolve(strict=False)
    except (OSError, RuntimeError) as err:
        # RuntimeError: symlink loop; OSError: other resolution failures.
        raise ValueError(f"could not resolve path under {base!r}: {err}") from err

    if base_real != candidate and base_real not in candidate.parents:
        logger.warning("Blocked path escape attempt: parts=%r base=%s", parts, base_real)
        raise ValueError(f"path {candidate} escapes base directory {base_real}")

    return candidate
