import asyncio
import json

import pytest
from bridge import Controller
from config import Settings


@pytest.mark.asyncio
async def test_local_java_requests_bypass_environment_proxy(monkeypatch):
    async def serve(reader, writer):
        await reader.readuntil(b'\r\n\r\n')
        body = json.dumps({'available': False}).encode()
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '
                     + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
        monkeypatch.setenv(key, 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    monkeypatch.setenv('no_proxy', '')
    monkeypatch.setenv('HAMLAB_API_URL', f'http://127.0.0.1:{port}/api')
    controller = Controller(Settings.load())
    try:
        assert await asyncio.wait_for(controller.api('/account/next'), 3) == {'available': False}
    finally:
        await controller.close()
        server.close()
        await server.wait_closed()
