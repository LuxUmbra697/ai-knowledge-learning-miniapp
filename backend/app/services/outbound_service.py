"""Bounded public HTTPS reads. DNS results are validated in the actual connector resolver."""
import asyncio
from dataclasses import dataclass
import ipaddress
import re
import socket

import aiohttp
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import ThreadedResolver
from yarl import URL


class OutboundRejected(ValueError):
    pass


_TRANSITION_NETWORKS = tuple(ipaddress.ip_network(value) for value in ('64:ff9b::/96', '64:ff9b:1::/48', '2002::/16', '2001::/32'))
_concurrency = asyncio.Semaphore(4)


def public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise OutboundRejected('DNS returned an invalid address') from error
    if (not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified
            or getattr(address, 'scope_id', None)):
        raise OutboundRejected('Non-public addresses are not allowed')
    if address.version == 6:
        if any(address in network for network in _TRANSITION_NETWORKS):
            raise OutboundRejected('IPv6 transition addresses are not allowed')
        if address.ipv4_mapped:
            public_address(str(address.ipv4_mapped))


def validate_url(value):
    if not isinstance(value, str) or len(value) > 4096 or '\\' in value or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise OutboundRejected('Invalid URL')
    try:
        url = URL(value)
        host = (url.host or '').rstrip('.').lower()
        if url.scheme != 'https' or url.port != 443 or url.user is not None or url.password is not None or not host:
            raise OutboundRejected('Only public HTTPS on port 443 without credentials is allowed')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.invalid', '.test'))
                    or re.fullmatch(r'[0-9.]+', host) or re.fullmatch(r'0[xX][0-9a-fA-F]+', host)):
                raise OutboundRejected('Internal or ambiguous hostnames are not allowed')
        else:
            public_address(host)
        return url
    except (ValueError, UnicodeError) as error:
        if isinstance(error, OutboundRejected):
            raise
        raise OutboundRejected('Invalid URL') from error


class PublicResolver(AbstractResolver):
    def __init__(self):
        self.resolver = ThreadedResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = await self.resolver.resolve(host, port, family)
        if not results:
            raise OutboundRejected('DNS returned no addresses')
        for result in results:
            public_address(result['host'])
        return results

    async def close(self):
        await self.resolver.close()


@dataclass(frozen=True)
class FetchedResource:
    content: bytes
    content_type: str
    url: str


async def _read(session, value, max_bytes, content_types):
    for _ in range(3):
        url = validate_url(value)
        async with session.get(url, allow_redirects=False) as response:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get('Location')
                if not location or any(ord(char) < 33 or ord(char) == 127 for char in location) or '\\' in location:
                    raise OutboundRejected('Invalid redirect')
                try:
                    value = str(url.join(URL(location)))
                except (ValueError, UnicodeError) as error:
                    raise OutboundRejected('Invalid redirect') from error
                continue
            if response.status != 200:
                raise OutboundRejected('Remote response was not successful')
            mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if mime not in content_types or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise OutboundRejected('Unsupported remote content type or encoding')
            declared = response.headers.get('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared) > max_bytes):
                raise OutboundRejected('Remote content exceeds the size limit')
            data = bytearray()
            async for block in response.content.iter_chunked(16384):
                if len(data) + len(block) > max_bytes:
                    raise OutboundRejected('Remote content exceeds the size limit')
                data.extend(block)
            return FetchedResource(bytes(data), mime, str(url))
    raise OutboundRejected('Too many redirects')


async def fetch_public(value, *, max_bytes, content_types, timeout=25):
    validate_url(value)
    if not 0 < max_bytes <= 8 * 1024 * 1024 or not 0 < timeout <= 30:
        raise ValueError('Outbound limits exceed the service budget')
    try:
        async with asyncio.timeout(timeout), _concurrency:
            resolver = PublicResolver()
            try:
                connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, force_close=True, limit=2)
                async with aiohttp.ClientSession(connector=connector, trust_env=False, cookie_jar=aiohttp.DummyCookieJar(),
                                                auto_decompress=False, headers={'Accept-Encoding': 'identity'},
                                                timeout=aiohttp.ClientTimeout(total=timeout, connect=5, sock_read=10)) as session:
                    return await _read(session, value, max_bytes, content_types)
            finally:
                await resolver.close()
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
        raise OutboundRejected('Remote content is temporarily unavailable') from error
