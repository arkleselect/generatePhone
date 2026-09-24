"""Local CLIProxyAPI OAuth adapter; reuse the existing durable Java task queue."""
import asyncio
import base64
import io
import os
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import httpx
from PIL import Image
from bridge import Controller
from dataset import now, validate_source


class ProxyController(Controller):
    channel = 'CLIPROXY_CODEX'
    login_required_message = '代理尚未加载账号授权，请点击登录 / 连接账号；浏览器成功页不代表令牌已保存'

    def __init__(self, settings):
        super().__init__(settings)
        root = Path(__file__).resolve().parents[2]
        self.binary = root / '.tools/cliproxy/cli-proxy-api'
        self.config = root / 'data/cliproxy/config.yaml'
        self.model = os.getenv('CLIPROXY_IMAGE_MODEL', 'gpt-image-2.5')
        self.process = self.login_process = None
        self.proxy = httpx.AsyncClient(base_url='http://127.0.0.1:8317', timeout=settings.timeout,
                                      trust_env=False, follow_redirects=False)
        self.message = 'CLIProxyAPI 账号执行器未连接'

    def status(self):
        return {**super().status(), 'engine': 'cliproxy', 'model': self.model}

    async def ensure_browser(self, headless=False):
        """The legacy hook now ensures the selected account transport is running."""
        if not self.binary.is_file() or not self.config.is_file():
            raise ValueError('请先按 README 安装并配置本机 CLIProxyAPI')
        key = self.config.with_name('client-key').read_text().strip()
        self.proxy.headers['Authorization'] = 'Bearer ' + key
        try:
            response = await self.proxy.get('/v1/models', timeout=2)
            if response.status_code == 200:
                return
            raise ValueError('本机 8317 端口已被其他服务占用，或代理认证配置不一致')
        except httpx.TransportError:
            pass
        if self.process is None or self.process.returncode is not None:
            with self.config.with_name('proxy.log').open('ab') as log:
                self.process = await asyncio.create_subprocess_exec(
                    str(self.binary), '-config', str(self.config), stdout=log, stderr=log, umask=0o077)
        for _ in range(30):
            await asyncio.sleep(.2)
            if self.process.returncode is not None:
                break
            try:
                if (await self.proxy.get('/v1/models', timeout=1)).status_code == 200:
                    return
            except httpx.TransportError:
                pass
        raise ValueError('CLIProxyAPI 启动失败，请检查 data/cliproxy/proxy.log')

    async def ready(self):
        try:
            response = await self.proxy.get('/v1/models', timeout=2)
            response.raise_for_status()
            models = response.json().get('data', [])
        except (httpx.HTTPError, ValueError):
            raise ValueError('无法读取本机 CLIProxyAPI 状态，请检查代理服务和本机客户端密钥') from None
        if not models:
            if self.login_process and self.login_process.returncode is not None:
                self.message = '账号授权未保存，请检查代理网络设置后重新连接账号'
            return False
        if not any(model.get('id') == self.model for model in models):
            raise ValueError(f'账号已加载，但代理未提供请求模型 {self.model}，请检查 CLIPROXY_IMAGE_MODEL 配置')
        return True

    async def start(self):
        await self.ensure_browser()
        return await super().start()

    async def login(self):
        if self.lock.locked():
            raise ValueError('当前任务正在执行，请先暂停并等待完成')
        async with self.lock:
            await self.ensure_browser()
            if self.phase != 'LOGIN_REQUIRED' and await self.ready():
                self.phase = 'READY'; self.message = '账号已连接，可开始自动执行；实际生图权限以请求结果为准'
            else:
                if self.login_process is None or self.login_process.returncode is not None:
                    with self.config.with_name('login.log').open('ab') as log:
                        self.login_process = await asyncio.create_subprocess_exec(
                            str(self.binary), '-config', str(self.config), '-codex-login',
                            stdout=log, stderr=log, stdin=asyncio.subprocess.PIPE, umask=0o077)
                self.phase = 'LOGIN'; self.message = '请在浏览器完成 Codex 账号授权，完成后再次点击连接账号'
        return self.status()

    async def callback(self, url):
        # Pass to the original OAuth process: it owns PKCE and validates state.
        if not isinstance(url, str) or len(url) > 16000 or any(c in url for c in '\r\n'):
            raise ValueError('请粘贴完整的单行回调网址')
        parsed = urlsplit(url.strip())
        query = parse_qs(parsed.query)
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')
                or parsed.port != 1455 or parsed.path != '/auth/callback'
                or not query.get('code') or not query.get('state')):
            raise ValueError('请粘贴包含 code 和 state 的 localhost:1455/auth/callback 完整网址，不是 /success 页面网址')
        async with self.lock:
            if not self.login_process or self.login_process.returncode is not None:
                raise ValueError('该次登录已结束，请重新点击连接账号并使用新回调网址')
            try:
                self.login_process.stdin.write((url.strip() + '\n').encode())
                await self.login_process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                raise ValueError('登录进程已结束，请重新连接账号') from None
            self.message = '回调已提交，正在等待代理完成令牌交换和保存'
        return self.status()

    async def execute_task(self, task, row, journal, allowed):
        if row['status'] == 'SUCCEEDED':
            return
        if row['status'] not in ('PENDING', 'LOGIN_REQUIRED', 'RATE_LIMITED'):
            journal.update(row, status='UNKNOWN', error='代理请求结果待核实，不会自动重复生图')
            return
        source = validate_source(row['source_image_path'])
        # Convert the reference and mask to identical PNG dimensions.
        with Image.open(source) as image:
            reference = io.BytesIO(); image.convert('RGBA').save(reference, format='PNG')
            files = {'image': ('reference.png', reference.getvalue(), 'image/png')}
            roi = task['params'].get('roi')
            if roi:
                response = await self.client.get(self.api_url + '/tasks/' + task['id'] + '/bundle',
                                                 headers={'X-HamLab-Request': '1'})
                response.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
                    files['mask'] = ('mask.png', bundle.read('edit-region-mask.png'), 'image/png')
        if not await allowed():
            return
        journal.update(row, status='SUBMITTING', attempts=row['attempts']+1, error=None)
        try:
            response = await self.proxy.post('/v1/images/edits', files=files,
                data={'model': self.model, 'prompt': row['prompt'], 'n': '1', 'response_format': 'b64_json'})
            if response.status_code in (401, 403, 429):
                status = 'RATE_LIMITED' if response.status_code == 429 else 'LOGIN_REQUIRED'
                journal.update(row, status=status, error=f'账号请求被拒绝（HTTP {response.status_code}），请检查授权或额度')
                return
            if response.status_code in (400, 404, 422):
                journal.update(row, status='FAILED', error=f'代理不支持当前模型或参数（HTTP {response.status_code}），请检查代理日志')
                return
            response.raise_for_status()
            data = response.json()
            raw = base64.b64decode(data['data'][0]['b64_json'], validate=True)
            target = Path(row['output_file_path']); temporary = target.with_suffix('.part')
            with Image.open(io.BytesIO(raw)) as output:
                if output.width * output.height > 24_000_000:
                    raise ValueError('Output is too large')
                output.convert('RGB').save(temporary, format='PNG')
            temporary.replace(target)
            journal.update(row, status='SUCCEEDED', generated_at=now(), error=None,
                           requested_model=self.model, actual_model=data.get('model'))
        except Exception as exc:
            journal.update(row, status='UNKNOWN', error='代理结果无法确认，不自动重发：' + type(exc).__name__)

    async def close(self):
        await super().close()
        await self.proxy.aclose()
        for process in (self.login_process, self.process):
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill(); await process.wait()
