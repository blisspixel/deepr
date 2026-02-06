"""
Network security for the Deepr MCP server.

Provides SSRF (Server-Side Request Forgery) protection by blocking
requests to internal/private IP ranges, and optional domain allowlisting.

Delegates IP resolution and blocking to deepr.utils.security for
consistent SSRF protection across the entire codebase.
"""

import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

from deepr.utils.security import is_blocked_ip, resolve_all_ips

logger = logging.getLogger("deepr.mcp.security")


def is_internal_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/internal range.

    Args:
        ip_str: IP address string (IPv4 or IPv6)

    Returns:
        True if the IP is internal/private
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return is_blocked_ip(ip)
    except ValueError:
        # If we can't parse it, block it to be safe
        return True


class SSRFProtector:
    """Validates URLs against SSRF attacks.

    Blocks requests to internal IPs and optionally enforces
    a domain allowlist for outbound requests.

    Resolves all IP addresses (IPv4 + IPv6) for a hostname and
    blocks if any resolve to an internal range.

    Usage:
        protector = SSRFProtector()
        protector.validate_url("https://api.openai.com/v1/chat")  # OK
        protector.validate_url("http://127.0.0.1/admin")  # raises ValueError

        # With allowlist:
        protector = SSRFProtector(allowed_domains=["api.openai.com", "api.x.ai"])
        protector.validate_url("https://evil.com")  # raises ValueError
    """

    def __init__(
        self,
        allowed_domains: Optional[list[str]] = None,
        audit_log: bool = True,
    ):
        """Initialize SSRF protector.

        Args:
            allowed_domains: If set, only these domains are permitted.
                           If None, all non-internal domains are allowed.
            audit_log: Whether to log all validated URLs
        """
        self._allowed_domains = set(allowed_domains) if allowed_domains else None
        self._audit_log = audit_log

    def validate_url(self, url: str) -> str:
        """Validate a URL is safe for outbound requests.

        Resolves all IPs (IPv4 + IPv6) for the hostname and blocks
        if any resolve to an internal range. Also blocks when DNS
        resolution fails entirely (conservative approach).

        Args:
            url: URL to validate

        Returns:
            The validated URL (unchanged)

        Raises:
            ValueError: If the URL targets an internal IP or blocked domain
        """
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            raise ValueError(f"SSRF blocked: no hostname in URL: {url}")

        # Check domain allowlist
        if self._allowed_domains and hostname not in self._allowed_domains:
            raise ValueError(f"SSRF blocked: domain '{hostname}' not in allowlist")

        # Resolve all IPs (IPv4 + IPv6) and check each
        ip_strings = resolve_all_ips(hostname)

        if not ip_strings:
            # DNS resolution failed -- block conservatively
            raise ValueError(f"SSRF blocked: DNS resolution failed for '{hostname}'")

        for ip_str in ip_strings:
            if is_internal_ip(ip_str):
                raise ValueError(f"SSRF blocked: '{hostname}' resolves to internal IP {ip_str}")

        if self._audit_log:
            logger.debug("URL validated: %s -> %s", hostname, ip_strings)

        return url

    def validate_ip(self, ip_str: str) -> str:
        """Validate an IP address is not internal.

        Args:
            ip_str: IP address to validate

        Returns:
            The validated IP (unchanged)

        Raises:
            ValueError: If the IP is internal
        """
        if is_internal_ip(ip_str):
            raise ValueError(f"SSRF blocked: internal IP {ip_str}")
        return ip_str
