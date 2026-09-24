"""Validate downloaded bytes and redirect boundaries without contacting ChatGPT."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from PIL import Image
import chatgpt


def response(data, status=200, location=None):
    return SimpleNamespace(status=status, ok=status==200, headers={'location':location} if location else {}, body=AsyncMock(return_value=data), dispose=AsyncMock())


async def test_download_validates_real_image_and_preserves_bytes(tmp_path, monkeypatch):
    buffer = BytesIO(); Image.new('RGB',(20,20),'red').save(buffer,format='PNG'); data=buffer.getvalue()
    request = SimpleNamespace(get=AsyncMock(return_value=response(data)))
    page = SimpleNamespace(context=SimpleNamespace(request=request))
    monkeypatch.setattr(chatgpt,'_last_image_src',AsyncMock(return_value='https://chatgpt.com/files/image'))
    file = await chatgpt.download_image(page,'sample',tmp_path)
    assert file.suffix == '.png' and file.read_bytes() == data
    request.get.assert_awaited_once_with('https://chatgpt.com/files/image', timeout=60000, max_redirects=0)


async def test_download_never_follows_untrusted_redirect(tmp_path, monkeypatch):
    request=SimpleNamespace(get=AsyncMock(return_value=response(b'',302,'https://unrelated.example/image')))
    page=SimpleNamespace(context=SimpleNamespace(request=request))
    monkeypatch.setattr(chatgpt,'_last_image_src',AsyncMock(return_value='https://chatgpt.com/files/image'))
    with pytest.raises(chatgpt.GenerationFailed):
        await chatgpt.download_image(page,'sample',tmp_path)
    assert request.get.await_count == 1 and not list(tmp_path.iterdir())


async def test_html_is_not_saved_as_png(tmp_path, monkeypatch):
    request=SimpleNamespace(get=AsyncMock(return_value=response(b'<html>login required</html>')))
    page=SimpleNamespace(context=SimpleNamespace(request=request))
    monkeypatch.setattr(chatgpt,'_last_image_src',AsyncMock(return_value='https://chatgpt.com/files/image'))
    with pytest.raises(Exception):
        await chatgpt.download_image(page,'sample',tmp_path)
    assert not list(tmp_path.iterdir())
