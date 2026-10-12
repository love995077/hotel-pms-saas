"""Rules for URLs this service will call on a tenant's behalf.

An outbound webhook URL is typed in by a hotel and then requested by our
servers, so left unchecked it is a way to reach things only our servers can
see (cloud metadata, internal admin ports, the database host). Two checks stop
that: the URL's shape is validated when it is saved, and the addresses its host
resolves to are validated every time it is called.
"""

import asyncio
import socket
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048


class OutboundUrlError(ValueError):
    """The URL, or the address it resolves to, must not be called."""


def is_public_address(address: IPv4Address | IPv6Address) -> bool:
    """True only for addresses routable on the public internet."""
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    # is_global is False for private, loopback, link-local, CGNAT, reserved and
    # unspecified ranges; multicast is excluded separately.
    return address.is_global and not address.is_multicast


def _literal_address(host: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(host)
    except ValueError:
        return None


def validate_outbound_url(url: str, *, allow_private: bool) -> str:
    """Check the shape of an outbound URL and return it normalised.

    `allow_private` is the local-development escape hatch: it also permits
    plain http and hosts such as localhost.
    """
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise OutboundUrlError(f"URL cannot be longer than {MAX_URL_LENGTH} characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise OutboundUrlError("Not a valid URL") from exc

    allowed_schemes = ("https", "http") if allow_private else ("https",)
    if parts.scheme not in allowed_schemes:
        raise OutboundUrlError("URL must start with https://")
    if not parts.hostname:
        raise OutboundUrlError("URL must include a host name")
    if parts.username is not None or parts.password is not None:
        raise OutboundUrlError("URL must not contain a user name or password")
    if parts.fragment:
        raise OutboundUrlError("URL must not contain a fragment (#...)")
    if port == 0:
        raise OutboundUrlError("Not a valid port")

    literal = _literal_address(parts.hostname)
    if literal is not None and not allow_private and not is_public_address(literal):
        raise OutboundUrlError("URL must point to a public address")
    return url


async def resolve_public_address(host: str, port: int, *, allow_private: bool) -> str:
    """Resolve `host` and return one address that is safe to connect to.

    Every address the name resolves to must be public, so a name with one
    public and one internal record cannot be used to slip through. The caller
    connects to the returned address itself, not to the name, which closes the
    window in which the name could be re-pointed between check and use.
    """
    literal = _literal_address(host)
    if literal is not None:
        addresses = [literal]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise OutboundUrlError(f"Could not resolve host '{host}'") from exc
        addresses = [ip_address(info[4][0]) for info in infos]
        if not addresses:
            raise OutboundUrlError(f"Could not resolve host '{host}'")

    if not allow_private and not all(is_public_address(address) for address in addresses):
        raise OutboundUrlError("URL must point to a public address")
    return str(addresses[0])
