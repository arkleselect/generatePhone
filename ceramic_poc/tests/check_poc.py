"""Small runnable regression check, using explicitly procedural test fixtures."""
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from ceramic_poc.data import validate,write_manifest,import_dataset
from ceramic_poc.generation import plan


def fails(call):
    try: call()
    except ValueError: return
    raise AssertionError('Expected validation failure')


def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for phase,count in [(1,30),(2,260)]:
            directory=root/f'phase{phase}';assert plan(directory,phase)==count
            import json
            rows=json.loads((directory/'plan.json').read_text())['rows']
            groups={}
            for row in rows: assert groups.setdefault(row['base_id'],row['split'])==row['split']
            assert sum(r['label']=='good' for r in rows)==(20 if phase==1 else 200)
            assert not any(r['label']=='bad' and r['split']=='train' for r in rows)
            for row in rows:
                if row['label']=='bad':
                    assert '{{location}}' not in row['prompt']
                    assert 'Severity severe' not in row['prompt']
                    assert '0.5' in row['prompt']
        standard=root/'standard';assert plan(standard,1,'standard')==30
        assert any('Severity severe' in row['prompt'] for row in json.loads((standard/'plan.json').read_text())['rows'])
        fails(lambda:plan(root/'invalid',1,'invisible'))
        import httpx
        from unittest.mock import patch
        from ceramic_poc.generation import generate
        key=root/'data/cliproxy/client-key';key.parent.mkdir(parents=True);key.write_text('test-only-key')
        requested=[]
        def server(request):
            if request.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':'test-image-model'}]})
            requested.append(json.loads(request.content)['model'])
            return httpx.Response(500,json={'error':{'code':'internal_server_error'}})
        client=httpx.Client
        failed=root/'failed';plan(failed)
        with patch('ceramic_poc.generation.SYSTEM',root),patch('ceramic_poc.generation.httpx.Client',lambda **kw:client(transport=httpx.MockTransport(server),**kw)):
            try:generate(failed,limit=1,model='test-image-model')
            except httpx.HTTPStatusError:pass
            else:raise AssertionError('HTTP 500 must stop generation')
        receipt=json.loads((failed/'receipts.json').read_text())['good_0001']
        assert requested==['test-image-model']
        assert receipt['state']=='UNKNOWN' and receipt['http_status']==500
        assert receipt['requested_model']=='test-image-model' and receipt['error_type']=='HTTPStatusError'
        dataset=root/'fixture';rows=[]
        rng=np.random.default_rng(0)
        for i,(split,label) in enumerate([('train','good'),('train','good'),('val','good'),('val','bad'),('test','good'),('test','bad')]):
            ident=f'fixture{i}';relative=f'{split}/{label}/{ident}.png';path=dataset/relative;path.parent.mkdir(parents=True,exist_ok=True)
            # Test fixture only, never used as generated ceramic data or reported as industrial results.
            pixels=np.clip(220+rng.normal(0,3,(1024,1024,3)),0,255).astype('uint8')
            if label=='bad': pixels[450:550,350:650]=30
            Image.fromarray(pixels).save(path)
            rows.append(dict(id=ident,file=relative,label=label,defect_type='stain' if label=='bad' else 'good',prompt='procedural test fixture',base_id=ident,seed='0',split=split,batch='self-check',source_type='TEST_FIXTURE'))
        write_manifest(dataset,rows);assert validate(dataset)['count']==6
        assert import_dataset(dataset,root/'copy')['count']==6
        fails(lambda:import_dataset(dataset,root/'copy'))
        rows[2]['base_id']=rows[0]['base_id'];write_manifest(dataset,rows);fails(lambda:validate(dataset))
        rows[2]['base_id']=rows[2]['id'];rows[0]['label']='bad';write_manifest(dataset,rows);fails(lambda:validate(dataset))
        rows[0]['label']='good';write_manifest(dataset,rows)
        from ceramic_poc.model import train,calibrate,Detector,tiles
        from ceramic_poc.evaluate import evaluate
        weights=train(dataset,root/'run',input_size=64,ratio=.05,device='cpu',log=print)
        model=calibrate(weights,dataset,'cpu')
        from ceramic_poc.profiles import register,attach_model,reference,profiles
        registry=root/'profiles.json'
        first=register('红色细包装','厂家 A','30g；固定光照',dataset,str(model),registry)
        second=register('黄色粗包装','厂家 B','60g',root/'copy','',registry)
        assert reference(first,registry)['model']==str(model.resolve())
        fails(lambda:register('红色细包装','','',dataset,'',registry))
        fails(lambda:register('  ','','',dataset,'',registry))
        fails(lambda:reference(second,registry))
        fails(lambda:attach_model(second,root/'copy',str(model),registry))
        fails(lambda:attach_model(first,root/'copy',str(model),registry))
        fails(lambda:register('未校准','','',dataset,str(weights),registry))
        import torch
        saved=torch.load(model,map_location='cpu',weights_only=True)
        saved['config']['dataset']=str((root/'copy').resolve())
        saved['config']['threshold']+=1
        other=root/'copy-model.pt';torch.save(saved,other)
        attach_model(second,root/'copy',str(other),registry)
        assert reference(second,registry)['model']==str(other.resolve())
        assert reference(first,registry)['model']==str(model.resolve())
        assert len(profiles(registry))==2
        detector=Detector.load(model,'cpu');prediction=detector.predict(dataset/rows[-1]['file'])
        assert np.isfinite(prediction['score']) and prediction['map'].shape==(1024,1024)
        clean=detector.predict(dataset/rows[-2]['file'])
        assert prediction['score']>clean['score'], 'Obvious black test-fixture defect must score higher than clean fixture'
        report=evaluate(model,dataset,root/'report','cpu');assert report['count']==2
        canvas=Image.new('RGB',(1024,1024));coverage=np.zeros((1024,1024),int)
        for (x,y,r,b),_ in tiles(canvas,512):coverage[y:b,x:r]+=1
        assert coverage.min()>0
        from ceramic_poc.ui import build_app
        assert build_app(dataset).config['components']
        print('PASS: plans, leakage guards, transactional import, pretrained PatchCore fit/save/load/calibration/inference/evaluation, independent packaging references and mismatch guards, tile coverage, Gradio construction')

if __name__=='__main__':main()
