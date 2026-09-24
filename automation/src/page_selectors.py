"""Central DOM fallbacks used by the upstream ChatGPT driver."""
import asyncio
import re
import time

COMPOSERS = ('#prompt-textarea[contenteditable="true"]', 'textarea#prompt-textarea', '[contenteditable="true"][role="textbox"]')
GENERATED = ('img[alt^="Generated image"]', 'img[alt^="生成的图片"]', 'img[alt^="已生成图片"]', 'img[alt^="已创建图片"]', '[data-message-author-role="assistant"] img[alt*="生成"]')
LOADING = '[data-testid="image-gen-loading-state-dots"], [data-testid="stop-button"]'


async def composer(page, timeout=30):
    """Prefer established upstream selectors, then localized accessible textboxes."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for selector in COMPOSERS:
            node = page.locator(selector).first
            if await node.is_visible():
                return node
        node = page.get_by_role('textbox', name=re.compile('与 ChatGPT 聊天|Message ChatGPT|Chat with ChatGPT', re.I)).first
        if await node.is_visible():
            return node
        await asyncio.sleep(0.3)
    raise TimeoutError('找不到 ChatGPT 输入框，请检查登录或页面改版')


async def send_button(page, timeout=30):
    """Wait for an enabled submit button; never submit using an unverified generic button."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for node in [page.locator('[data-testid="send-button"]').first,
                     page.get_by_role('button', name=re.compile(r'^(发送提示词|发送消息|Send prompt|Send message)$', re.I)).first]:
            if await node.is_visible() and await node.is_enabled():
                return node
        await asyncio.sleep(0.3)
    raise TimeoutError('发送按钮不可用，参考图可能未上传成功')
