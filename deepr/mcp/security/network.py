"""
Network security for the Deepr MCP server.

Provides SSRF (Server-Side Request Forgery) protection by blocking
requests to internal/private IP ranges, and optional domain allowlisting.
"""

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("deepr.mcp.security")

# Private/internal IP ranges that should never be accessed by research
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # Private class A
    ipaddress.ip_network("172.16.0.0/12"),      # Private class B
    ipaddress.ip_network("192.168.0.0/16"),     # Private class C
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


def is_internal_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/internal range.

    Args:
        ip_str: IP address string (IPv4 or IPv6)

    Returns:
        True if the IP is internal/private
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in BLOCKED_NETWORKS)
    except ValueError:
        # If we can't parse it, block it to be safe
        return True


def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve a hostname to its IP address.

    Returns None if resolution fails.
    """
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return None


class SSRFProtector:
    """Validates URLs against SSRF attacks.

    Blocks requests to internal IPs and optionally enforces
    a domain allowlist for outbound requests.

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
            raise ValueError(
                f"SSRF blocked: domain '{hostname}' not in allowlist"
            )

        # Resolve hostname and check IP
        ip = resolve_hostname(hostname)
        if ip and is_internal_ip(ip):
            raise ValueError(
                f"SSRF blocked: '{hostname}' resolves to internal IP {ip}"
            )

        if self._audit_log:
            logger.debug("URL validated: %s -> %s", hostname, ip or "unresolved")

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
