"""Dataset plans, atomic manifests, bounded phase-aware retries and PNG output."""
import asyncio
import csv
import hashlib
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
import chatgpt
from browser import check_login_status
from config import Settings
from prompts import DEFECTS, defect_key, build_defect_prompt


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class GenerateRequest(BaseModel):
    """CLI and HTTP use the same validated request instead of independent business rules."""
    source_image_path: str
    defect_type: str
    count: int = Field(default=1, ge=1, le=5000)
    output_dir: str | None = None
    date_text: str | None = None
    batch_name: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    custom_prompt_suffix: str = Field(default='', max_length=4000)
    headless: bool | None = None
    max_retry: int | None = Field(default=None, ge=0, le=10)


def validate_source(value):
    """Validate real image content before any upload or browser launch."""
    try:
        source = Path(value).expanduser().resolve(strict=True)
        if not source.is_file() or not 0 < source.stat().st_size <= 20*1024*1024:
            raise ValueError('参考图为空或超过20MB')
        with Image.open(source) as image:
            if image.format not in ('PNG', 'JPEG') or image.width*image.height > 24_000_000:
                raise ValueError('参考图必须为不超过2400万像素的 PNG/JPEG')
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError('参考图不存在、不可读或格式无效') from exc
    return source


def atomic_json(file, value):
    """An interrupted write never replaces the last complete task snapshot."""
    temporary = file.with_suffix(file.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(file)


class Journal:
    """One durable manifest per batch; expected labels remain separate from manual review."""
    def __init__(self, directory, metadata):
        self.directory = Path(directory)
        self.metadata = metadata
        self.logger = logging.getLogger('dataset.' + metadata['batch_id'])
        self.logger.setLevel(Settings.load().log_level)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = logging.FileHandler(self.directory / 'run.log', encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            self.logger.addHandler(handler)

    @classmethod
    def create(cls, request: GenerateRequest, settings: Settings):
        source = validate_source(request.source_image_path)
        key = defect_key(request.defect_type)
        # Validate the prompt before creating directories, then freeze each sample independently.
        prompt = build_defect_prompt(key, request.date_text, request.custom_prompt_suffix)
        name = request.batch_name or ('batch_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
        directory = Path(request.output_dir or settings.output_dir).expanduser().resolve() / name
        directory.mkdir(parents=True, exist_ok=False)
        metadata = {'batch_id': name, 'status': 'QUEUED', 'created_at': now(), 'output_dir': str(directory), 'tasks': [],
                    'max_retry': settings.max_retry if request.max_retry is None else request.max_retry,
                    'headless': settings.headless if request.headless is None else request.headless,
                    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        journal = cls(directory, metadata)
        for index in range(1, request.count+1):
            journal.add(str(uuid.uuid4()), source, key, prompt if index == 1 else build_defect_prompt(key, request.date_text, request.custom_prompt_suffix), index, request.date_text)
        journal.save(); journal.logger.info('Created %d planned samples', request.count)
        return journal

    @classmethod
    def load(cls, directory):
        directory = Path(directory).resolve()
        return cls(directory, json.loads((directory / 'metadata.json').read_text(encoding='utf-8')))

    def add(self, task_id, source, key, prompt, index, date_text=None):
        definition = DEFECTS[defect_key(key)]
        folder = self.directory / definition['datasetType']; folder.mkdir(exist_ok=True)
        # Keep the original stem (including Chinese names), replacing only unsafe filename characters.
        stem = re.sub(r'[^\w.-]+', '_', Path(source).stem).strip('._')[:80] or 'image'
        row = {'task_id': task_id, 'source_image_path': str(source), 'defect_type': definition['datasetType'],
               'prompt': prompt, 'date_text': date_text, 'status': 'PENDING', 'created_at': now(), 'generated_at': None,
               'output_file_path': str(folder / f'{stem}_{definition["datasetType"]}_{index:03d}.png'),
               'retry_count': 0, 'attempts': 0, 'conversation_url': None, 'error': None, 'synthetic': True, 'review': 'PENDING', 'actual_model': None}
        self.metadata['tasks'].append(row)
        return row

    def save(self):
        atomic_json(self.directory / 'metadata.json', self.metadata)
        columns = ['task_id','source_image_path','defect_type','date_text','prompt','generated_at','output_file_path','status','retry_count','error','review']
        temporary = self.directory / 'tasks.csv.tmp'
        with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
            for row in self.metadata['tasks']:
                values = {key: row.get(key) for key in columns}
                # CSV consumers may execute formulas, so neutralize only dangerous leading characters.
                writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k,v in values.items()})
        temporary.replace(self.directory / 'tasks.csv')

    def update(self, row, **values):
        row.update(values); self.save()
        self.logger.info('Task %s status=%s retries=%s error=%s', row['task_id'], row['status'], row['retry_count'], row.get('error'))

    def summary(self):
        tasks = self.metadata['tasks']
        return {'task_id': self.metadata['batch_id'], 'status': self.metadata['status'], 'success_count': sum(t['status']=='SUCCEEDED' for t in tasks),
                'failed_count': sum(t['status'] in ('FAILED','DENIED','UNKNOWN') for t in tasks),
                'pending_count': sum(t['status'] not in ('SUCCEEDED','FAILED','DENIED','UNKNOWN') for t in tasks),
                'output_dir': str(self.directory), 'files': [t['output_file_path'] for t in tasks if t['status']=='SUCCEEDED'],
                'metadata_path': str(self.directory / 'metadata.json'), 'tasks_csv_path': str(self.directory / 'tasks.csv')}


async def run_one(page, row, journal, settings, before_submit=None):
    """Retry safe phases; a submitted timeout re-waits the same conversation, never re-submits."""
    limit = journal.metadata['max_retry']
    async def retry(exc, phase):
        if row['retry_count'] >= limit:
            return False
        journal.update(row, retry_count=row['retry_count']+1, error=f'{phase}: {type(exc).__name__}')
        await asyncio.sleep(min(2**row['retry_count'], 10))
        return True

    if row['status'] == 'SUCCEEDED':
        return
    if row['status'] in ('SUBMITTING','UNKNOWN'):
        journal.update(row, status='UNKNOWN', error='提交结果不明，需核实原会话；不会自动重复发送')
        return
    submitted = row['status'] in ('GENERATING','DOWNLOADING')
    if submitted:
        url = row.get('conversation_url') or ''
        if not re.fullmatch(r'https://chatgpt\.com/c/[A-Za-z0-9-]+', url):
            journal.update(row, status='UNKNOWN', error='无法恢复生成会话，请人工核实')
            return
        await page.goto(url, wait_until='domcontentloaded')
    while True:
        if not submitted:
            try:
                journal.update(row, status='UPLOADING', attempts=row['attempts']+1, error=None)
                await chatgpt.start_new_chat(page)
                if not await check_login_status(page):
                    journal.update(row, status='LOGIN_REQUIRED', error='请先登录 ChatGPT')
                    return
                await chatgpt.upload_reference(page, Path(row['source_image_path']))
                await chatgpt.type_prompt(page, row['prompt'])
                await chatgpt.send_button(page, timeout=120)
                if before_submit and not await before_submit():
                    journal.update(row, status='PENDING', error=None)
                    return
            except Exception as exc:
                if await retry(exc, 'upload'):
                    continue
                journal.update(row, status='FAILED', error='参考图上传或页面定位失败：' + type(exc).__name__)
                return
            journal.update(row, status='SUBMITTING')
            try:
                await chatgpt.submit_prompt(page)
            except Exception as exc:
                journal.update(row, status='UNKNOWN', error='发送动作结果不明：' + type(exc).__name__)
                return
            submitted = True
            journal.update(row, status='GENERATING', conversation_url=page.url)
        try:
            if row['status'] != 'DOWNLOADING':
                await chatgpt.wait_for_image_generation(page, 0, settings.timeout)
                journal.update(row, status='DOWNLOADING', conversation_url=page.url)
            downloaded = await chatgpt.download_image(page, 'original', journal.directory / '.originals')
            target = Path(row['output_file_path']); temporary = target.with_suffix('.part')
            with Image.open(downloaded) as image:
                if image.format == 'PNG':
                    shutil.copyfile(downloaded, temporary)
                else:
                    image.convert('RGB').save(temporary, format='PNG')
            temporary.replace(target)
            journal.update(row, status='SUCCEEDED', generated_at=now(), original_download_path=str(downloaded), error=None)
            return
        except chatgpt.RateLimited:
            journal.update(row, status='RATE_LIMITED', error='账号额度限制，暂停后续任务')
            return
        except chatgpt.ContentDenied:
            journal.update(row, status='DENIED', error='网页拒绝该请求，不自动重试')
            return
        except chatgpt.GenerationTimeout as exc:
            journal.update(row, conversation_url=page.url)
            if await retry(exc, 'wait_same_conversation'):
                continue
            journal.update(row, status='UNKNOWN', error='生成超时，需核实原会话；未重复提交')
            return
        except Exception as exc:
            if row['status'] == 'DOWNLOADING':
                if await retry(exc, 'download_same_image'):
                    continue
                journal.update(row, error='下载失败，可恢复同一会话继续下载：' + type(exc).__name__)
                return
            if isinstance(exc, chatgpt.GenerationFailed) and await retry(exc, 'explicit_generation_failure'):
                submitted = False
                continue
            journal.update(row, status='UNKNOWN', error='生成状态无法确认：' + type(exc).__name__)
            return


async def run_dataset(page, journal, settings, before_submit=None):
    """Serial execution preserves source independence; interruptions leave a resumable journal."""
    journal.metadata['status'] = 'RUNNING'; journal.save()
    for row in journal.metadata['tasks']:
        if row['status'] in ('SUCCEEDED', 'DENIED', 'FAILED'):
            continue
        await run_one(page, row, journal, settings, before_submit=before_submit)
        if row['status'] == 'PENDING':
            journal.metadata['status'] = 'PAUSED'; journal.save()
            return journal.summary()
        if row['status'] in ('UNKNOWN','RATE_LIMITED','LOGIN_REQUIRED','DOWNLOADING'):
            journal.metadata['status'] = 'NEEDS_ATTENTION'; journal.save()
            return journal.summary()
    journal.metadata['status'] = 'COMPLETED'; journal.save()
    return journal.summary()
