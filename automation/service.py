"""Optional local HTTP adapter; importing this module never opens a browser."""
import asyncio
import hmac
import logging
import os
import re
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from bridge import Controller
from config import Settings
from dataset import GenerateRequest, Journal, validate_source


def create_app(settings=None, controller_factory=None):
    settings = settings or Settings.load()
    if controller_factory is None:
        if os.getenv('ACCOUNT_ENGINE', 'browser') == 'cliproxy':
            from proxy import ProxyController
            controller_factory = ProxyController
        else:
            controller_factory = Controller
    token = os.getenv('CONTROL_TOKEN')
    if not token:
        raise ValueError('CONTROL_TOKEN is required; use main.py serve to create a local token file')

    @asynccontextmanager
    async def lifespan(app):
        controller = controller_factory(settings); app.state.controller = controller
        task = asyncio.create_task(controller.loop())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await controller.close()

    app = FastAPI(title='Industrial ChatGPT Image Batcher', lifespan=lifespan)
    app.state.jobs = {}

    @app.middleware('http')
    async def local_auth(request: Request, call_next):
        """Use a process secret, reject cross-site origins, and never enable wildcard CORS."""
        if request.headers.get('origin') or request.headers.get('sec-fetch-site') == 'cross-site' or not hmac.compare_digest(request.headers.get('x-worker-token',''), token):
            return JSONResponse({'message':'Forbidden'},status_code=403)
        response = await call_next(request); response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({'message': str(exc)},status_code=400)

    @app.exception_handler(Exception)
    async def failed(_request, exc):
        logging.getLogger(__name__).error('Worker request failed', exc_info=exc)
        return JSONResponse({'message': '浏览器执行器操作失败，请检查 Chrome 连接授权和 data/browser/worker.log'}, status_code=500)

    @app.get('/status')
    async def status():
        return app.state.controller.status()

    @app.post('/login')
    async def login():
        return await app.state.controller.login()

    @app.post('/callback')
    async def callback(body: dict):
        controller = app.state.controller
        if getattr(controller, 'channel', '') != 'CLIPROXY_CODEX':
            raise ValueError('当前执行模式不支持提交 OAuth 回调')
        return await controller.callback(body.get('url'))

    @app.post('/start')
    async def start():
        return await app.state.controller.start()

    @app.post('/pause')
    async def pause():
        return app.state.controller.pause()

    @app.post('/generate-defects', status_code=202)
    async def generate(request: GenerateRequest):
        if getattr(app.state.controller, 'channel', '') == 'CLIPROXY_CODEX':
            raise ValueError('CLIProxyAPI 模式请在 Java/Vue 页面创建和确认任务')
        source_path = Path(request.source_image_path).expanduser()
        source = validate_source(source_path if source_path.is_absolute() else settings.input_root / source_path)
        output = Path(request.output_dir or settings.output_dir).expanduser()
        output = (output if output.is_absolute() else settings.output_dir.parent / output).resolve()
        if not source.is_relative_to(settings.input_root) or output != settings.output_dir:
            raise ValueError('HTTP 输入/输出路径必须位于 INPUT_ROOT / DATASET_ROOT 内')
        request = request.model_copy(update={'source_image_path': str(source), 'output_dir': str(output)})
        try:
            journal = Journal.create(request, settings)
        except FileExistsError as exc:
            raise HTTPException(409, '批次目录已存在，请更换名称或恢复该批次') from exc
        app.state.jobs[journal.metadata['batch_id']] = journal
        await app.state.controller.pending.put(journal)
        return journal.summary()
    def find_job(job_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', job_id):
            raise HTTPException(404)
        journal = app.state.jobs.get(job_id)
        if journal is None:
            directory = (settings.output_dir / job_id).resolve()
            if not directory.is_relative_to(settings.output_dir):
                raise HTTPException(404)
            if not (directory / 'metadata.json').is_file():
                raise HTTPException(404)
            journal = Journal.load(directory)
            if journal.metadata['status'] in ('RUNNING','QUEUED'):
                journal.metadata['status'] = 'NEEDS_ATTENTION'; journal.save()
            app.state.jobs[job_id] = journal
        return journal

    @app.get('/jobs/{job_id}')
    async def job(job_id: str):
        return find_job(job_id).summary()

    @app.get('/jobs/{job_id}/tasks')
    async def job_tasks(job_id: str):
        return find_job(job_id).metadata

    @app.post('/jobs/{job_id}/resume')
    async def resume(job_id: str):
        journal = find_job(job_id)
        if journal.metadata['status'] in ('RUNNING','QUEUED'):
            raise HTTPException(409, '任务已经在队列中')
        journal.metadata['status'] = 'QUEUED'; journal.save()
        await app.state.controller.pending.put(journal)
        return journal.summary()
    return app
