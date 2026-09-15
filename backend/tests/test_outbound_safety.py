import asyncio
import socket
from unittest.mock import AsyncMock

import pytest

from app.services import outbound_service as outbound


@pytest.mark.parametrize('url', [
    'http://example.org/file', 'file:///etc/passwd', 'https://localhost/file',
    'https://localhost./', 'https://127.0.0.1/', 'https://127.1/', 'https://2130706433/',
    'https://0x7f000001/', 'https://10.0.0.1/', 'https://172.16.0.1/', 'https://192.168.1.1/',
    'https://169.254.169.254/latest/meta-data/', 'https://100.64.0.1/', 'https://0.0.0.0/',
    'https://[::1]/', 'https://[::ffff:127.0.0.1]/', 'https://[fe80::1%25eth0]/',
    'https://[64:ff9b::a00:1]/', 'https://[2002:0a00:0001::]/', 'https://[ff02::1]/',
    'https://user:password@example.org/', 'https://example.org:8443/', 'https://example.org/\r\nheader',
    'https://example.org\\@127.0.0.1/', 'https://service.internal/', 'https://service.local/',
])
def test_untrusted_urls_cannot_target_local_or_ambiguous_addresses(url):
    with pytest.raises(outbound.OutboundRejected):
        outbound.validate_url(url)


@pytest.mark.parametrize('url', ['https://example.org/path?q=one', 'https://beef.cafe/', 'https://8.8.8.8/', 'https://[2606:4700:4700::1111]/'])
def test_public_https_urls_keep_their_query_and_hostname(url):
    assert str(outbound.validate_url(url)) == url


@pytest.mark.asyncio
async def test_dns_results_are_checked_before_the_connector_receives_them(monkeypatch):
    resolver = outbound.PublicResolver()
    lookup = AsyncMock(return_value=[{'host': '8.8.8.8', 'port': 443, 'family': socket.AF_INET},
                                    {'host': '127.0.0.1', 'port': 443, 'family': socket.AF_INET}])
    monkeypatch.setattr(resolver.resolver, 'resolve', lookup)
    try:
        with pytest.raises(outbound.OutboundRejected):
            await resolver.resolve('attacker.example', 443)
        lookup.return_value = [{'host': '8.8.8.8', 'port': 443, 'family': socket.AF_INET}]
        assert (await resolver.resolve('public.example', 443))[0]['host'] == '8.8.8.8'
    finally:
        await resolver.close()


class Response:
    def __init__(self, data=b'ok', status=200, headers=None):
        self.data, self.status, self.headers = data, status, headers or {'Content-Type': 'image/png'}
        self.content = self
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): pass
    async def iter_chunked(self, _size):
        for offset in range(0, len(self.data), 2): yield self.data[offset:offset + 2]


class Session:
    def __init__(self, responses): self.responses, self.calls = responses, []
    def get(self, url, **kwargs):
        self.calls.append((str(url), kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_redirect_is_revalidated_before_following_and_never_carries_auth():
    session = Session([Response(status=302, headers={'Location': 'https://169.254.169.254/'})])
    with pytest.raises(outbound.OutboundRejected):
        await outbound._read(session, 'https://example.org/image', 100, {'image/png'})
    assert len(session.calls) == 1 and session.calls[0][1]['allow_redirects'] is False
    assert 'headers' not in session.calls[0][1] and 'auth' not in session.calls[0][1]


@pytest.mark.asyncio
async def test_redirect_loop_stops_after_three_requests():
    session = Session([Response(status=302, headers={'Location': '/again'}) for _ in range(4)])
    with pytest.raises(outbound.OutboundRejected):
        await outbound._read(session, 'https://example.org/image', 100, {'image/png'})
    assert len(session.calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [Response(b'12345'), Response(b'x', headers={'Content-Length': '100', 'Content-Type': 'image/png'}),
                                     Response(b'<script/>', headers={'Content-Type': 'image/svg+xml'}), Response(status=404)])
async def test_response_size_type_and_status_fail_closed(response):
    with pytest.raises(outbound.OutboundRejected):
        await outbound._read(Session([response]), 'https://example.org/image', 4, {'image/png'})


@pytest.mark.asyncio
async def test_bounded_public_response_is_returned_with_final_location():
    session = Session([Response(status=302, headers={'Location': '/final?q=1'}), Response(b'png')])
    result = await outbound._read(session, 'https://example.org/image', 10, {'image/png'})
    assert result.content == b'png' and result.url == 'https://example.org/final?q=1'
    assert result.content_type == 'image/png'


@pytest.mark.asyncio
async def test_real_connector_rejects_rebound_dns_before_opening_socket(monkeypatch):
    lookup = AsyncMock(return_value=[{'hostname': 'attacker.example', 'host': '127.0.0.1', 'port': 443,
                                     'family': socket.AF_INET, 'proto': 0, 'flags': 0}])
    connect = AsyncMock(side_effect=AssertionError('A rejected address reached the connection stage'))
    monkeypatch.setattr(outbound.ThreadedResolver, 'resolve', lookup)
    monkeypatch.setattr(outbound.aiohttp.TCPConnector, '_wrap_create_connection', connect)
    with pytest.raises(outbound.OutboundRejected):
        await outbound.fetch_public('https://attacker.example/', max_bytes=100, content_types={'image/png'})
    lookup.assert_awaited_once()
    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_total_timeout_includes_admission_wait(monkeypatch):
    monkeypatch.setattr(outbound, '_concurrency', asyncio.Semaphore(0))
    with pytest.raises(outbound.OutboundRejected):
        await outbound.fetch_public('https://example.org/', max_bytes=100, content_types={'image/png'}, timeout=0.01)


@pytest.mark.asyncio
async def test_malformed_redirect_has_a_safe_error():
    session = Session([Response(status=302, headers={'Location': 'https://[bad'})])
    with pytest.raises(outbound.OutboundRejected):
        await outbound._read(session, 'https://example.org/image', 100, {'image/png'})
