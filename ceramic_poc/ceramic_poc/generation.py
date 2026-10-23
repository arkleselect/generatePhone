"""Prompt export and durable generation using the existing local CLIProxyAPI."""
import base64
import io
import json
import random
import time
from pathlib import Path

import httpx
from PIL import Image
from .data import write_manifest

PROJECT = Path(__file__).resolve().parents[1]
SYSTEM = PROJECT.parent


def plan(directory, phase=1, difficulty='subtle'):
    if difficulty not in {'standard','subtle'}: raise ValueError('Invalid defect difficulty')
    directory = Path(directory)
    if directory.exists():
        raise ValueError('Plan directory already exists')
    rng = random.Random(20261008)
    normal_count = 20 if phase == 1 else 200
    counts = {'scratch':4,'crack':3,'stain':3} if phase == 1 else dict.fromkeys(['scratch','crack','stain'],20)
    train_count, val_count = (12,4) if phase == 1 else (160,20)
    templates={name:(PROJECT/'prompts'/f'{name}{"_subtle" if name!="good" and difficulty=="subtle" else ""}.txt').read_text().strip() for name in ['good',*counts]}
    rows=[]
    for i in range(normal_count):
        ident=f'good_{i+1:04d}'
        split='train' if i < train_count else 'val' if i < train_count+val_count else 'test'
        x,y=rng.uniform(-1,1),rng.uniform(-1,1)
        prompt=templates['good']+f'\nGenerate exactly one new independent image. Subtle natural ceramic texture variation, no patterned texture. Center offset: horizontal {x:.2f}% and vertical {y:.2f}%. Do not add any text or sample identifier.'
        rows.append(dict(id=ident,file=f'{split}/good/{ident}.png',label='good',defect_type='good',prompt=prompt,base_id=ident,seed='',split=split,batch=f'phase{phase}_normal',source_type='AI'))
    used={'val':0,'test':0}
    for category,count in counts.items():
        for i in range(count):
            split='val' if i < (count+1)//2 else 'test'
            bases=[r for r in rows if r['label']=='good' and r['split']==split]
            base=bases[used[split]%len(bases)]; used[split]+=1
            ident=f'{category}_{i+1:04d}'
            severity=['mild','moderate','severe'][i%3]
            # Normalized coordinates refer to the image; keep the defect on the central tile.
            x,y=rng.uniform(.25,.75),rng.uniform(.25,.75)
            prompt=templates[category]+f'\nOne image only, 1024x1024. Defect center approximately ({x:.2f}, {y:.2f}) in normalized image coordinates, staying within the tile. Severity {severity}. Natural irregular geometry; length {rng.uniform(3,16):.1f}% of tile width, width appropriate to this defect and severity, orientation {rng.randrange(180)} degrees. No text or watermark.'
            if difficulty=='subtle':
                prompt=templates[category].replace('{{location}}',f'{x:.2f}, {y:.2f}')+f'\nNatural irregular direction approximately {rng.randrange(180)} degrees.'
            rows.append(dict(id=ident,file=f'{split}/bad/{ident}.png',label='bad',defect_type=category,prompt=prompt,base_id=base['id'],seed='',split=split,batch=f'phase{phase}_edit',source_type='AI'))
    directory.mkdir(parents=True)
    (directory/'plan.json').write_text(json.dumps({'phase':phase,'difficulty':difficulty,'planning_seed':20261008,'image_generation_seed':None,'rows':rows},ensure_ascii=False,indent=2))
    write_manifest(directory,rows)
    (directory/'prompts.json').write_text(json.dumps({r['id']:r['prompt'] for r in rows},ensure_ascii=False,indent=2))
    return len(rows)


def generate(directory, limit=None, model='gpt-image-2.5'):
    directory=Path(directory).resolve()
    rows=json.loads((directory/'plan.json').read_text())['rows']
    receipt=directory/'receipts.json'
    status=json.loads(receipt.read_text()) if receipt.exists() else {}
    key=(SYSTEM/'data/cliproxy/client-key').read_text().strip()
    def save():
        temp=receipt.with_suffix('.tmp'); temp.write_text(json.dumps(status,ensure_ascii=False,indent=2)); temp.replace(receipt)
    done=0
    with httpx.Client(base_url='http://127.0.0.1:8317',headers={'Authorization':'Bearer '+key},timeout=900,trust_env=False) as client:
        models=client.get('/v1/models'); models.raise_for_status()
        if not any(m['id']==model for m in models.json().get('data',[])):
            raise ValueError(f'Existing system does not expose {model}; select an available model explicitly')
        for row in rows:
            ident=row['id']; target=directory/row['file']
            if status.get(ident,{}).get('state')=='SUCCEEDED':
                if not target.is_file(): raise ValueError(f'Missing saved result {ident}')
                continue
            if ident in status:
                raise ValueError(f'{ident} has an unresolved/rejected request; inspect receipts before retrying')
            if limit is not None and done>=limit: break
            if (directory/'pause-after-current').exists():
                print('Paused before the next request; completed outputs preserved',flush=True)
                break
            reference=None
            if row['label']=='bad':
                base=next(r for r in rows if r['id']==row['base_id'])
                reference=directory/base['file']
                if not reference.is_file(): raise ValueError(f'Missing clean base {reference}')
            status[ident]={'state':'SUBMITTING','submitted_at':time.time(),'requested_model':model}; save()
            print(f'Generating {ident} ({row["split"]}/{row["label"]})',flush=True)
            try:
                payload={'model':model,'prompt':row['prompt'],'n':1,'size':'1024x1024','response_format':'b64_json'}
                if reference:
                    with reference.open('rb') as handle:
                        response=client.post('/v1/images/edits',data={k:str(v) for k,v in payload.items()},files={'image':('base.png',handle,'image/png')})
                else:
                    response=client.post('/v1/images/generations',json=payload)
                if response.status_code in (400,401,403,404,422,429):
                    status[ident].update(state='REJECTED',http_status=response.status_code); save()
                    raise ValueError(f'Generation rejected HTTP {response.status_code}; check existing system account/limits, no automatic retry')
                response.raise_for_status()
                result=response.json(); raw=base64.b64decode(result['data'][0]['b64_json'],validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    original=directory/'originals'/f'{ident}.bin'; original.parent.mkdir(exist_ok=True); original.write_bytes(raw)
                    status[ident]['original_size']=list(image.size)
                    status[ident]['resized_to_1024']=image.size!=(1024,1024)
                    if image.width!=image.height or min(image.size)<1024:
                        raise ValueError(f'Unexpected generated shape {image.size}; original preserved')
                    image=image.resize((1024,1024),Image.Resampling.LANCZOS) if image.size!=(1024,1024) else image
                    target.parent.mkdir(parents=True,exist_ok=True)
                    temporary=target.with_suffix('.part'); image.convert('RGB').save(temporary,format='PNG'); temporary.replace(target)
                status[ident].update(state='SUCCEEDED',actual_model=result.get('model'),image_seed=result.get('seed'),finished_at=time.time())
                save(); done+=1
                print(f'Saved {target}',flush=True)
            except Exception as error:
                status[ident]['error_type']=type(error).__name__
                if isinstance(error,httpx.HTTPStatusError):
                    status[ident]['http_status']=error.response.status_code
                if status[ident]['state']=='SUBMITTING': status[ident]['state']='UNKNOWN'
                save()
                raise
    return {'completed':sum(r['state']=='SUCCEEDED' for r in status.values()),'planned':len(rows)}
