
import socket
import time
from ipaddress import ip_address
from urllib.parse import urlparse

import requests


TIMEOUT_SECONDS = 5


# Reserved example domains that we want to treat as DOWN
# for this project's monitoring purposes.
RESERVED_EXAMPLE_DOMAINS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
}


def is_public_url(url: str) -> bool:
    """
    Accept only HTTP/HTTPS URLs that resolve to public IP addresses.
    Reject localhost, private/internal addresses, and invalid domains.
    """
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        hostname = parsed.hostname.lower()

        if hostname == "localhost" or hostname.endswith(".localhost"):
            return False

        port = parsed.port or (
            443 if parsed.scheme == "https" else 80
        )

        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )

        if not addresses:
            return False

        for address in addresses:
            ip = ip_address(address[4][0])

            if not ip.is_global:
                return False

        return True

    except (ValueError, socket.gaierror, OSError):
        return False


def check_url(url: str) -> dict:
    """
    Check website reachability and measure response time.

    DOWN:
        Reserved example domains, invalid/private URLs, HTTP 5xx,
        timeouts, or connection failures.

    UP:
        A reachable website that returns an HTTP response below 500,
        including HTTP 403 and 404.
    """

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # 1. Reject reserved example domains for this project.
    if hostname in RESERVED_EXAMPLE_DOMAINS:
        return {
            "is_success": False,
            "status_code": None,
            "response_time_ms": None,
            "error_type": "ReservedExampleDomain",
            "error_message": (
                "This is a reserved example domain, not a "
                "website intended for real monitoring."
            ),
        }

    # 2. Reject invalid URLs and non-public destinations.
    if not is_public_url(url):
        return {
            "is_success": False,
            "status_code": None,
            "response_time_ms": None,
            "error_type": "InvalidOrPrivateURL",
            "error_message": (
                "The URL is invalid or points to a non-public address."
            ),
        }

    # 3. Send a request to the website.
    start_time = time.perf_counter()

    try:
        response = requests.get(
            url,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
            headers={
                "User-Agent": "API-Uptime-Monitor/1.0"
            },
        )

        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000
        )

        # A response below 500 means the server responded.
        # This includes 403 Forbidden and 404 Not Found.
        is_success = response.status_code < 500

        return {
            "is_success": is_success,
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "error_type": (
                None if is_success else "HTTPServerError"
            ),
            "error_message": (
                None
                if is_success
                else (
                    f"Server returned HTTP "
                    f"{response.status_code}"
                )
            ),
        }

    except requests.exceptions.Timeout:
        return {
            "is_success": False,
            "status_code": None,
            "response_time_ms": round(
                (time.perf_counter() - start_time) * 1000
            ),
            "error_type": "Timeout",
            "error_message": (
                f"The website did not respond within "
                f"{TIMEOUT_SECONDS} seconds."
            ),
        }

    except requests.exceptions.RequestException as exc:
        return {
            "is_success": False,
            "status_code": None,
            "response_time_ms": round(
                (time.perf_counter() - start_time) * 1000
            ),
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        }
