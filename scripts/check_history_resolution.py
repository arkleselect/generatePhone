"""Run with automation/.venv/bin/python scripts/check_history_resolution.py.
Requires the frontend on 5173; every API request is mocked, no real data changes.
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def check(browser, initial):
    page = await browser.new_page()
    task = {'id': 'task-test', 'inputId': 'image-test', 'status': initial, 'attempts': 1,
            'outputId': None, 'prompt': 'test', 'params': {'baseDate': '20260924', 'pose': {'kind': 'original'}},
            'settings': {}, 'error': None}
    batch = {'id': 'batch-test', 'status': 'PAUSED', 'mode': 'ACCOUNT', 'stage': 'POSE', 'created_at': '2026-09-24T00:00:00Z'}
    removed = False
    async def route(request):
        nonlocal removed
        path = request.request.url.split('/api', 1)[1]
        method = request.request.method
        if path == '/browser/status': data = {'enabled': False, 'phase': 'READY', 'message': 'test'}
        elif path == '/batches' and method == 'GET': data = [] if removed else [batch]
        elif path == '/batches/batch-test' and method == 'GET': data = {'batch': batch, 'tasks': [task]}
        elif path == '/batches/batch-test' and method == 'DELETE':
            assert task['status'] == 'FAILED'
            removed = True; data = None
        elif path == '/tasks/task-test/' + ('resolve' if initial == 'UNKNOWN' else 'failure') and method == 'POST':
            task['status'] = 'FAILED'; data = None
        elif path in ['/assets', '/tasks']: data = []
        elif path == '/defects': data = {}
        elif path == '/config': data = {'settings': {}, 'executionMode': 'ACCOUNT'}
        else:
            raise AssertionError(f'Unexpected request {method} {path}')
        await request.fulfill(status=200, content_type='application/json', body=json.dumps(data))
    await page.route('**/api/**', route)
    await page.goto('http://127.0.0.1:5173')
    await page.get_by_role('button', name='任务与历史', exact=True).click()
    await page.get_by_role('combobox', name='选择历史批次').click()
    await page.get_by_role('option').first.click()
    delete = page.get_by_role('button', name='删除批次', exact=True)
    assert await delete.is_disabled()
    await page.get_by_role('button', name='确认无结果，结束任务', exact=True).click()
    await page.get_by_role('button', name='已核实，结束任务', exact=True).click()
    await page.wait_for_function("!document.querySelector('.queue-actions button.el-button--danger').disabled")
    await delete.click()
    await page.locator('.el-message-box').get_by_role('button', name='删除批次', exact=True).click()
    await page.get_by_text('尚未创建批次', exact=True).wait_for()
    assert removed
    await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        try:
            for state in ['AWAITING_IMAGE', 'UNKNOWN']:
                await check(browser, state)
                print(state, 'resolve and delete passed')
        finally:
            await browser.close()

asyncio.run(main())
