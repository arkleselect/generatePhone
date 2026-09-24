from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import browser


@pytest.mark.asyncio
async def test_existing_chrome_uses_logged_in_context_and_only_disconnects(tmp_path, monkeypatch):
    (tmp_path / 'DevToolsActivePort').write_text('9222\n/devtools/browser/test-id\n')
    monkeypatch.setenv('BROWSER_EXISTING_CHROME_DIR', str(tmp_path))
    page = object()
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    connect = AsyncMock(return_value=SimpleNamespace(contexts=[context]))
    pw = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect), stop=AsyncMock())
    monkeypatch.setattr(browser, 'async_playwright', lambda: SimpleNamespace(start=AsyncMock(return_value=pw)))
    actual = await browser.launch_browser()
    assert actual == (pw, context, page)
    connect.assert_awaited_once_with('ws://127.0.0.1:9222/devtools/browser/test-id', timeout=60000)
    await browser.close_browser(pw, context)
    context.close.assert_not_awaited()
    pw.stop.assert_awaited_once()


@pytest.mark.parametrize('content', ['', '0\n/devtools/browser/a', '9222\n//remote-host/a'])
def test_invalid_endpoint_is_actionable(tmp_path, content):
    (tmp_path / 'DevToolsActivePort').write_text(content)
    with pytest.raises(ValueError, match='chrome://inspect'):
        browser.existing_chrome_endpoint(tmp_path)


@pytest.mark.asyncio
async def test_owned_browser_is_closed():
    pw = SimpleNamespace(stop=AsyncMock())
    context = SimpleNamespace(close=AsyncMock())
    await browser.close_browser(pw, context)
    context.close.assert_awaited_once()
    pw.stop.assert_awaited_once()
