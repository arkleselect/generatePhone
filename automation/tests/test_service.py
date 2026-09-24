"""Local HTTP contracts validated in-process; the stub never opens a browser."""
import asyncio
from dataclasses import replace
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from config import Settings
from service import create_app


class IdleController:
    def __init__(self, _settings):
        self.pending = asyncio.Queue()
    async def loop(self):
        await asyncio.Event().wait()
    async def close(self):
        return
    def status(self):
        return {'phase': 'STOPPED', 'enabled': False}


def test_http_auth_paths_and_queue(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_TOKEN','offline-test-token')
    source = tmp_path / 'images/ham.png'; source.parent.mkdir(); Image.new('RGB',(16,16)).save(source)
    settings = replace(Settings.load(), input_root=source.parent, output_dir=tmp_path/'dataset')
    with TestClient(create_app(settings, IdleController)) as client:
        headers = {'X-Worker-Token': 'offline-test-token'}
        assert client.get('/status').status_code == 403
        assert client.get('/status', headers=headers).json()['phase'] == 'STOPPED'
        assert client.get('/status', headers={**headers,'Origin':'https://example.com'}).status_code == 403
        body = {'source_image_path': str(source), 'defect_type':'blur','count':2,'batch_name':'api_batch'}
        result = client.post('/generate-defects', headers=headers, json=body)
        assert result.status_code == 202, result.text
        job = result.json(); assert job['pending_count'] == 2 and job['success_count'] == 0
        assert client.get('/jobs/api_batch/tasks', headers=headers).json()['tasks'][0]['defect_type']=='blur'
        assert client.post('/generate-defects', headers=headers, json=body).status_code == 409
        assert client.post('/generate-defects', headers=headers, json={**body,'batch_name':'other','output_dir':str(tmp_path)}).status_code == 400
        assert client.post('/generate-defects', headers=headers, json={**body,'defect_type':'bad'}).status_code == 400
        assert client.post('/jobs/api_batch/resume', headers=headers).status_code == 409
