"""Upstream persistent-browser lifecycle, extended with configuration and a profile lock."""
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright
from config import Settings

ROOT = str(Path(__file__).resolve().parents[1])
PROFILE_DIR = str(Settings.load().profile_dir)
logger = logging.getLogger(__name__)


def existing_chrome_endpoint(directory):
    """Use Chrome's opt-in debugging endpoint without reading cookies."""
    try:
        port, path = (Path(directory).expanduser() / 'DevToolsActivePort').read_text().splitlines()[:2]
        if not port.isdecimal() or not 1 <= int(port) <= 65535 or not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]+', path):
            raise ValueError('Invalid debugging endpoint')
        return f'ws://127.0.0.1:{port}{path}'
    except (OSError, ValueError) as exc:
        raise ValueError('请先在已登录的 Chrome 中打开 chrome://inspect/#remote-debugging 并启用远程调试，再点击登录 / 打开浏览器') from exc


class ProfileLock:
    """OS file lock prevents CLI, HTTP and Java from sharing one active browser profile."""
    def __init__(self, profile):
        self.path = Path(profile) / '.hamlab.lock'
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.write(b'0'); self.file.flush(); self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close(); self.file = None
            raise RuntimeError('浏览器配置正在使用，请先关闭另一执行器或 CLI') from exc

    def release(self):
        """Closing the handle releases the OS lock even after an interrupted process."""
        if self.file:
            self.file.close(); self.file = None


async def launch_browser(headless: bool = False, settings=None):
    """Keep the upstream (playwright, persistent context, page) return contract."""
    settings = settings or Settings.load()
    existing = os.getenv('BROWSER_EXISTING_CHROME_DIR', '').strip()
    if existing:
        endpoint = existing_chrome_endpoint(existing)
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(endpoint, timeout=60000)
            context = browser.contexts[0]
            # Track ownership: never close the user's browser or its existing tabs.
            pw._hamlab_attached = True
            page = await context.new_page()
            return pw, context, page
        except BaseException:
            await pw.stop()
            raise
    profile = settings.profile_dir
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        profile.chmod(0o700)
    lock = ProfileLock(profile); lock.acquire()
    pw = None
    try:
        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            str(profile), headless=headless, viewport={'width': 1280, 'height': 900},
            accept_downloads=True, **({'channel': settings.channel} if settings.channel else {}))
        context.on('close', lambda *_: lock.release())
        # One-time migration of the session explicitly saved by the previous local worker.
        old = settings.state_dir / 'state.json'
        marker = profile / '.session-imported'
        if old.exists() and not marker.exists():
            state = json.loads(old.read_text(encoding='utf-8'))
            await context.add_cookies(state.get('cookies', []))
            origins = state.get('origins', [])
            await context.add_init_script(script='''(() => {
                const origins = %s;
                const origin = origins.find(item => item.origin === location.origin);
                if (origin) for (const item of origin.localStorage || []) localStorage.setItem(item.name, item.value);
            })();''' % json.dumps(origins).replace('</', '<\\/'))
            marker.write_text('imported\n', encoding='utf-8')
        page = context.pages[0] if context.pages else await context.new_page()
        return pw, context, page
    except BaseException:
        lock.release()
        if pw:
            await pw.stop()
        raise


async def check_login_status(page) -> bool:
    """A guest composer is not proof of login; require the visible profile control."""
    if page.is_closed() or any(value in page.url.lower() for value in ['auth.openai.com', '/auth/login', '/login']):
        return False
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            login = page.get_by_role('button', name=re.compile(r'^(登录|Log in)$', re.I))
            profile = page.locator('[data-testid="accounts-profile-button"]')
            if await login.first.is_visible():
                return False
            if await profile.first.is_visible() or await page.get_by_role(
                'button', name=re.compile(r'个人资料.*菜单|profile.*menu', re.I)).first.is_visible():
                return True
            await asyncio.sleep(0.25)
        return False
    except Exception:
        logger.warning('无法检查登录状态；请查看浏览器')
        return False


async def close_browser(pw, context):
    """Attempt both cleanups; an already-closed window is an expected user action."""
    try:
        if not getattr(pw, '_hamlab_attached', False):
            await context.close()
    except Exception:
        logger.info('浏览器窗口已关闭')
    finally:
        await pw.stop()


async def login_session():
    """Preserve upstream auth: log in interactively, then close the browser to save the profile."""
    pw, context, page = await launch_browser(headless=False)
    try:
        await page.goto('https://chatgpt.com/', wait_until='domcontentloaded')
        print('请在浏览器登录；完成后关闭窗口。登录状态保存在本机浏览器配置目录。', flush=True)
        while not page.is_closed():
            await asyncio.sleep(0.5)
    finally:
        await close_browser(pw, context)
