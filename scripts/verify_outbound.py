"""One public HTTPS asset read; no credentials, model requests or object-store writes."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.outbound_service import OutboundRejected, fetch_public


async def main():
    if sys.argv[1:] != ['--confirm-one-public-read']:
        raise SystemExit('Pass --confirm-one-public-read to allow one bounded public asset request')
    start = time.monotonic()
    result = await fetch_public('https://www.python.org/static/img/python-logo.png',
                                max_bytes=128 * 1024, content_types={'image/png'}, timeout=25)
    assert result.content.startswith(b'\x89PNG\r\n\x1a\n')
    blocked = 0
    for value in ('https://127.0.0.1/', 'https://169.254.169.254/latest/meta-data/', 'https://[::1]/'):
        try:
            await fetch_public(value, max_bytes=1024, content_types={'image/png'})
        except OutboundRejected:
            blocked += 1
    assert blocked == 3
    evidence = {'measured_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'public_source': 'https://www.python.org/static/img/python-logo.png',
                'network_requests': 1, 'model_calls': 0, 'object_store_writes': 0,
                'download_bytes': len(result.content), 'content_type': result.content_type,
                'sha256': hashlib.sha256(result.content).hexdigest(), 'blocked_before_network': blocked,
                'elapsed_ms': round((time.monotonic() - start) * 1000),
                'limitations': ['Not a real image-model or COS integration test',
                                'Redirect and mixed DNS cases are covered by deterministic tests, not this public read',
                                'PNG signature only; image decoding and dimension verification remain pending']}
    (ROOT / 'docs/evidence/m3-outbound-live.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence))


if __name__ == '__main__':
    asyncio.run(main())
