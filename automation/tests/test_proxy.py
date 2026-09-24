import io
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from config import Settings
from dataset import Journal
from proxy import ProxyController


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'timeout', 'quota', 'unauthorized'])
async def test_proxy_reference_mask_and_no_duplicate_submission(tmp_path, outcome):
    source = tmp_path / 'reference.png'
    Image.new('RGB', (100, 100), 'red').save(source)
    settings = replace(Settings.load(), state_dir=tmp_path, output_dir=tmp_path)
    journal = Journal(tmp_path, {'batch_id': 'proxy-test', 'tasks': [], 'max_retry': 0})
    row = journal.add('task', source, 'normal', 'Edit only the date', 1)
    calls = []
    async def respond(request):
        calls.append(request)
        body = await request.aread()
        assert request.url.path == '/v1/images/edits'
        assert b'filename="reference.png"' in body and b'filename="mask.png"' in body
        assert b'Edit only the date' in body
        from email.parser import BytesParser
        from email.policy import default
        parts = BytesParser(policy=default).parsebytes(
            ('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+body)
        mask = next(part.get_payload(decode=True) for part in parts.iter_parts() if part.get_filename() == 'mask.png')
        with Image.open(io.BytesIO(mask)) as image:
            assert image.getpixel((25, 35))[3] == 0
            assert image.getpixel((0, 0))[3] == 255
        if outcome == 'timeout':
            raise httpx.ReadTimeout('uncertain')
        if outcome in ('quota', 'unauthorized'):
            return httpx.Response(429 if outcome == 'quota' else 401)
        import base64
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(source.read_bytes()).decode()}]})
    controller = ProxyController(settings)
    await controller.proxy.aclose()
    controller.proxy = httpx.AsyncClient(base_url='http://127.0.0.1:8317', transport=httpx.MockTransport(respond))
    import zipfile
    mask = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
    from PIL import ImageDraw
    ImageDraw.Draw(mask).rectangle((20, 30, 69, 49), fill=(0, 0, 0, 0))
    buffer = io.BytesIO(); mask.save(buffer, format='PNG')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('edit-region-mask.png', buffer.getvalue())
    controller.client.get = AsyncMock(return_value=httpx.Response(200, content=archive.getvalue(),
        request=httpx.Request('GET', 'http://127.0.0.1:8080/api/tasks/task/bundle')))
    task = {'id': 'task', 'params': {'roi': {'x': .2, 'y': .3, 'width': .5, 'height': .2}}}
    try:
        await controller.execute_task(task, row, journal, AsyncMock(return_value=True))
        assert row['status'] == {'success': 'SUCCEEDED', 'timeout': 'UNKNOWN',
                                 'quota': 'RATE_LIMITED', 'unauthorized': 'LOGIN_REQUIRED'}[outcome]
        if outcome in ('success', 'timeout'):
            await controller.execute_task(task, row, journal, AsyncMock(return_value=True))
            assert len(calls) == 1
        if outcome == 'success':
            assert row.get('actual_model') is None
            with Image.open(row['output_file_path']) as image:
                assert image.format == 'PNG'
    finally:
        await controller.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('models,expected', [([], False), ([{'id':'gpt-image-2.5'}], True), ([{'id':'text-only'}], 'model')])
async def test_oauth_readiness_distinguishes_auth_from_model(models, expected):
    controller = ProxyController(Settings.load())
    await controller.proxy.aclose()
    controller.proxy = httpx.AsyncClient(base_url='http://127.0.0.1:8317',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'data':models})))
    controller.ensure_browser = AsyncMock()
    try:
        if expected == 'model':
            with pytest.raises(ValueError, match='账号已加载.*模型'):
                await controller.start()
        elif expected:
            assert (await controller.start())['enabled'] is True
        else:
            with pytest.raises(ValueError, match='代理尚未加载账号授权'):
                await controller.start()
            assert controller.enabled is False
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_callback_goes_only_to_original_login_process():
    from types import SimpleNamespace
    from unittest.mock import Mock
    controller = ProxyController(Settings.load())
    pipe = SimpleNamespace(write=Mock(), drain=AsyncMock())
    controller.login_process = SimpleNamespace(returncode=None, stdin=pipe)
    url = 'http://localhost:1455/auth/callback?code=test-code&state=test-state'
    try:
        await controller.callback(url)
        pipe.write.assert_called_once_with((url+'\n').encode())
        for invalid in ['http://localhost:1455/success', url+'\nextra', url.replace('localhost', 'example.com')]:
            with pytest.raises(ValueError):
                await controller.callback(invalid)
        controller.login_process.returncode = 0
        with pytest.raises(ValueError, match='登录已结束'):
            await controller.callback(url)
        assert pipe.write.call_count == 1
    finally:
        await controller.close()
