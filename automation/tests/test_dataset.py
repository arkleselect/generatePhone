"""Offline dataset and failure-recovery tests: no ChatGPT account or generation calls."""
import csv
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from PIL import Image
import chatgpt
import dataset
from config import Settings
from dataset import GenerateRequest, Journal, run_dataset, run_one
from prompts import DEFECTS, build_defect_prompt, defect_key


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / 'ham001.png'; Image.new('RGB', (24,24), 'red').save(source)
    settings = replace(Settings.load(), output_dir=tmp_path / 'dataset', input_root=tmp_path, state_dir=tmp_path / 'state', profile_dir=tmp_path / 'profile', max_retry=2)
    return source, settings


@pytest.fixture
def driver(monkeypatch, setup):
    source, _ = setup
    page = type('Page', (), {'url': 'https://chatgpt.com/c/abc-123', 'goto': AsyncMock()})()
    for name in ['start_new_chat','upload_reference','type_prompt','submit_prompt','wait_for_image_generation','send_button']:
        monkeypatch.setattr(chatgpt, name, AsyncMock())
    monkeypatch.setattr(chatgpt, 'download_image', AsyncMock(return_value=source))
    monkeypatch.setattr(dataset, 'check_login_status', AsyncMock(return_value=True))
    monkeypatch.setattr(dataset.asyncio, 'sleep', AsyncMock())
    return page


def plan(setup, count=1, name=None):
    source, settings = setup
    return Journal.create(GenerateRequest(source_image_path=str(source), defect_type='date_missing', count=count, batch_name=name, date_text='2026.09.24'), settings)


def test_required_catalog_and_prompts():
    required = ['date_missing','date_incomplete','code_dropout','broken_print','blur','faint','stain','misalignment','ghosting','normal']
    for key in required:
        assert defect_key(key) in DEFECTS
        prompt = build_defect_prompt(key, '2026.09.24', '轻微自然变化')
        assert '仅修改生产日期' in prompt and '2026.09.24' in prompt
        assert '不做海报风' in prompt and '轻微自然变化' in prompt
    assert defect_key('印染') == 'ink_transfer'
    assert '擦拖细纹' in build_defect_prompt('印染', '2026.09.24')
    assert '印染可以位于日期之外' in build_defect_prompt('印染', '2026.09.24')
    with pytest.raises(ValueError):
        build_defect_prompt('blur', '2026.02.30')


def test_manifest_no_overwrite_and_invalid_source(setup):
    journal = plan(setup, 2, 'test_batch')
    manifest = json.loads((journal.directory / 'metadata.json').read_text())
    assert len(manifest['tasks']) == 2
    assert manifest['tasks'][0]['output_file_path'].endswith('date_missing/ham001_date_missing_001.png')
    assert len(list(csv.DictReader((journal.directory / 'tasks.csv').open(encoding='utf-8-sig')))) == 2
    with pytest.raises(FileExistsError):
        plan(setup, 1, 'test_batch')
    bad = setup[0].parent / 'bad.png'; bad.write_text('not an image')
    with pytest.raises(Exception):
        Journal.create(GenerateRequest(source_image_path=str(bad), defect_type='normal'), setup[1])


async def test_each_sample_uses_fresh_source_and_png(driver, setup):
    journal = plan(setup, 3)
    result = await run_dataset(driver, journal, setup[1])
    assert result['success_count'] == 3 and result['status'] == 'COMPLETED'
    assert chatgpt.upload_reference.await_count == 3 and chatgpt.start_new_chat.await_count == 3
    assert all(call.args[1] == setup[0] for call in chatgpt.upload_reference.await_args_list)
    for file in result['files']:
        with Image.open(file) as image:
            assert image.format == 'PNG'


async def test_timeout_retries_wait_not_submission(driver, setup):
    journal = plan(setup); row = journal.metadata['tasks'][0]
    chatgpt.wait_for_image_generation.side_effect = [chatgpt.GenerationTimeout('timeout'), None]
    await run_one(driver, row, journal, setup[1])
    assert row['status'] == 'SUCCEEDED' and row['retry_count'] == 1
    assert chatgpt.submit_prompt.await_count == 1


async def test_download_retry_keeps_same_generation(driver, setup):
    journal = plan(setup); row = journal.metadata['tasks'][0]
    chatgpt.download_image.side_effect = [OSError('network'), setup[0]]
    await run_one(driver, row, journal, setup[1])
    assert row['status'] == 'SUCCEEDED' and row['retry_count'] == 1
    assert chatgpt.submit_prompt.await_count == 1 and chatgpt.wait_for_image_generation.await_count == 1


async def test_ambiguous_click_never_resubmits(driver, setup):
    journal = plan(setup, 2); row = journal.metadata['tasks'][0]
    chatgpt.submit_prompt.side_effect = TimeoutError('click')
    result = await run_dataset(driver, journal, setup[1])
    assert result['status'] == 'NEEDS_ATTENTION' and row['status'] == 'UNKNOWN'
    await run_one(driver, row, journal, setup[1])
    assert chatgpt.submit_prompt.await_count == 1
    assert journal.metadata['tasks'][1]['status'] == 'PENDING'


async def test_upload_retry_and_explicit_generation_retry(driver, setup):
    journal = plan(setup); row = journal.metadata['tasks'][0]
    chatgpt.upload_reference.side_effect = [OSError('upload'), None, None]
    chatgpt.wait_for_image_generation.side_effect = [chatgpt.GenerationFailed('explicit'), None]
    await run_one(driver, row, journal, setup[1])
    assert row['status'] == 'SUCCEEDED' and row['retry_count'] == 2
    assert chatgpt.upload_reference.await_count == 3 and chatgpt.submit_prompt.await_count == 2


async def test_rate_limit_and_cancellation_stop(driver, setup):
    journal = plan(setup, 2)
    chatgpt.wait_for_image_generation.side_effect = chatgpt.RateLimited('limit')
    await run_dataset(driver, journal, setup[1])
    assert journal.metadata['tasks'][0]['status'] == 'RATE_LIMITED'
    assert journal.metadata['tasks'][1]['status'] == 'PENDING'
    other = plan(setup)
    await run_one(driver, other.metadata['tasks'][0], other, setup[1], before_submit=AsyncMock(return_value=False))
    assert other.metadata['tasks'][0]['status'] == 'PENDING'
    assert chatgpt.submit_prompt.await_count == 1


async def test_interrupted_receipt_never_replays(driver, setup):
    journal = plan(setup); row = journal.metadata['tasks'][0]; row['status'] = 'SUBMITTING'
    await run_one(driver, row, journal, setup[1])
    assert row['status'] == 'UNKNOWN'
    chatgpt.submit_prompt.assert_not_awaited()


def test_profile_lock(setup):
    from browser import ProfileLock
    first = ProfileLock(setup[1].profile_dir); second = ProfileLock(setup[1].profile_dir)
    first.acquire()
    try:
        with pytest.raises(RuntimeError):
            second.acquire()
    finally:
        first.release()
    second.acquire(); second.release()


def test_casing_defects_keep_date_normal():
    for key in ['casing_tear', 'seam_weld', 'clip_burst', 'bent']:
        prompt = build_defect_prompt(key, '2026.09.24')
        assert '日期本身不施加缺陷' in prompt and '仅修改生产日期' not in prompt
        assert '红色或金色' in prompt and '{location}' not in prompt
    assert '弯曲形状除外' in build_defect_prompt('弯曲产品', '2026.09.24')
