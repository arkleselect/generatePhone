"""Connect the existing Java task queue to the upstream Python browser functions."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
import httpx
from browser import launch_browser, close_browser, check_login_status
from dataset import Journal, run_dataset, run_one, validate_source, now

logger = logging.getLogger(__name__)


class Controller:
    """One browser owner and one work loop prevent competing CLI/HTTP submissions."""
    channel = 'BROWSER_CHATGPT'
    login_required_message = '请先打开浏览器并登录'
    def __init__(self, settings):
        self.settings = settings
        self.pw = self.context = self.page = None
        self.lock = asyncio.Lock()
        self.enabled = False
        self.paused = False
        self.headless = None
        self.phase = 'STOPPED'
        self.message = '浏览器执行器未启动'
        self.task_id = None
        self.pending = asyncio.Queue()
        self.closed = False
        self.api_url = os.getenv('HAMLAB_API_URL', '')
        if self.api_url and not re.fullmatch(r'http://127\.0\.0\.1:\d+/api', self.api_url):
            raise ValueError('HAMLAB_API_URL must point to a local Java service')
        self.client = httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False)

    def status(self):
        return {'phase': self.phase, 'message': self.message, 'enabled': self.enabled, 'taskId': self.task_id,
                'engine': 'chatgpt-image-batcher/python'}

    async def ensure_browser(self, headless=False):
        """The persistent profile is reused for both interactive and headless runs."""
        if self.page and not self.page.is_closed() and self.headless == headless:
            return
        if self.context:
            await close_browser(self.pw, self.context)
        self.pw, self.context, self.page = await launch_browser(headless=headless, settings=self.settings)
        self.headless = headless
        await self.page.goto('https://chatgpt.com/', wait_until='domcontentloaded')

    async def login(self):
        if self.lock.locked():
            raise ValueError('当前任务正在执行，请先暂停并等待当前任务完成')
        async with self.lock:
            await self.ensure_browser(False)
            await self.page.bring_to_front()
            self.phase = 'READY' if await check_login_status(self.page) else 'LOGIN'
            self.message = '已登录；状态保存在本机' if self.phase == 'READY' else '请在浏览器中登录'
        return self.status()

    async def start(self):
        if self.lock.locked():
            raise ValueError('已有任务执行中')
        if not await self.ready():
            raise ValueError(self.login_required_message)
        self.enabled = True; self.paused = False; self.phase = 'IDLE'; self.message = '自动执行已开启，等待已确认任务'
        return self.status()

    async def ready(self):
        return bool(self.page) and await check_login_status(self.page)

    async def execute_task(self, task, row, journal, allowed):
        await run_one(self.page, row, journal, self.settings, before_submit=allowed)

    def pause(self):
        self.enabled = False; self.paused = True
        self.message = '已暂停领取后续任务，当前已提交图片仍会保存'
        return self.status()

    async def api(self, route, method='GET', **kwargs):
        response = await self.client.request(method, self.api_url + route, headers={'X-HamLab-Request': '1'}, **kwargs)
        if response.is_error:
            raise RuntimeError('本地 Java 接口失败：HTTP ' + str(response.status_code))
        return response.json() if response.content else None

    def bridge_journal(self, task, reference):
        """Reuse task ids as receipts and append tasks into the same batch dataset."""
        if not re.fullmatch(r'[a-f0-9-]{36}', task['batchId']) or not re.fullmatch(r'[a-f0-9-]{36}', task['id']):
            raise ValueError('任务标识无效')
        directory = self.settings.output_dir / ('java_' + task['batchId'])
        if (directory / 'metadata.json').exists():
            journal = Journal.load(directory)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            journal = Journal(directory, {'batch_id': 'java_' + task['batchId'], 'status': 'RUNNING', 'created_at': now(),
                'output_dir': str(directory), 'tasks': [], 'max_retry': self.settings.max_retry, 'headless': self.settings.headless})
        row = next((row for row in journal.metadata['tasks'] if row['task_id'] == task['id']), None)
        if row is None:
            params = task['params']; defect = params.get('defect')
            row = journal.add(task['id'], reference, defect['type'] if defect else 'normal', task['prompt'], len(journal.metadata['tasks'])+1, params['baseDate'])
            row['java_batch_id'] = task['batchId']; row['root_source_id'] = task['rootSourceId']
            # Never replay an ambiguous submission from the superseded Node worker.
            legacy = self.settings.state_dir / (task['id'] + '.json')
            if legacy.exists():
                row['status'] = 'UNKNOWN'; row['error'] = '存在旧执行器回执，请先核实旧会话并手动回填，禁止自动重发'
            journal.save()
        return journal, row

    async def next_java(self):
        next_task = await self.api('/account/next')
        if not next_task.get('available'):
            self.phase = 'IDLE'; self.message = '等待已确认任务'; self.task_id = None
            return
        task = next_task['task']; self.task_id = task['id']
        detail = await self.api('/batches/' + task['batchId'])
        if detail['batch']['status'] != 'ACTIVE':
            self.phase = 'PAUSED'; self.message = '当前批次暂停或已取消'
            return
        reference = validate_source(next_task['reference_path'])
        journal, row = self.bridge_journal(task, reference)
        async def allowed():
            """Recheck persisted cancellation immediately before any browser submission."""
            latest = await self.api('/batches/' + task['batchId'])
            return self.enabled and latest['batch']['status'] == 'ACTIVE'
        self.phase = 'RUNNING'; self.message = '正在执行任务 ' + task['id'][:8]
        await self.execute_task(task, row, journal, allowed)
        if row['status'] == 'SUCCEEDED':
            # Retry only the local import after a connection failure, never the image generation.
            data = Path(row['output_file_path']).read_bytes()
            await self.api('/tasks/' + task['id'] + '/result', 'POST', files={'file': ('generated.png', data, 'image/png')},
                           data={'actualModel': row.get('actual_model') or '', 'channel': self.channel})
            journal.update(row, java_imported=True)
            self.phase = 'IDLE'; self.message = '结果已保存，等待下一任务'
        elif row['status'] in ('FAILED','DENIED','UNKNOWN'):
            await self.api('/tasks/' + task['id'] + '/failure', 'POST', json={'reason': row.get('error') or row['status'], 'uncertain': row['status']=='UNKNOWN'})
            if row['status'] == 'UNKNOWN':
                self.enabled = False
                current = await self.api('/batches/' + task['batchId'])
                if current['batch']['status'] == 'ACTIVE':
                    await self.api('/batches/' + task['batchId'] + '/pause', 'POST')
            self.phase = 'ERROR'; self.message = row.get('error') or row['status']
        elif row['status'] != 'PENDING':
            self.enabled = False; self.phase = row['status']; self.message = row.get('error') or '任务需要检查'

    async def standalone_allowed(self):
        return not self.paused and not self.closed

    async def loop(self):
        """Process explicit standalone jobs or confirmed Java work, never both concurrently."""
        while not self.closed:
            journal = None
            try:
                if not self.paused and not self.pending.empty():
                    journal = await self.pending.get()
                    async with self.lock:
                        await self.ensure_browser(journal.metadata['headless'])
                        self.phase = 'RUNNING'; self.task_id = journal.metadata['batch_id']
                        await run_dataset(self.page, journal, self.settings, before_submit=self.standalone_allowed)
                        self.phase = journal.metadata['status']; self.message = '独立任务：' + self.phase
                    self.pending.task_done()
                elif self.enabled and self.api_url:
                    async with self.lock:
                        await self.ensure_browser(self.settings.headless)
                        if not await self.ready():
                            self.enabled = False; self.phase = 'LOGIN'; self.message = '请在浏览器确认登录状态'
                        else:
                            await self.next_java()
                elif self.phase == 'LOGIN' and await self.ready():
                    self.phase = 'READY'; self.message = '已登录，状态保存在本机'
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.enabled = False; self.phase = 'ERROR'; self.message = '执行停止：' + type(exc).__name__ + '，请检查 run.log 和浏览器'
                logger.error('Browser work stopped: %s', type(exc).__name__)
                if journal is not None and journal.metadata['status'] in ('RUNNING','QUEUED'):
                    journal.metadata['status'] = 'NEEDS_ATTENTION'; journal.save()
            await asyncio.sleep(2)

    async def close(self):
        self.closed = True; self.enabled = False
        if self.context:
            await close_browser(self.pw, self.context)
        await self.client.aclose()
