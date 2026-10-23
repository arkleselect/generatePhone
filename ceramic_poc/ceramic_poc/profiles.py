"""Packaging references share the detector code, not their normal feature banks."""
import json
import math
import uuid
from pathlib import Path

from .data import validate

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / 'runs' / 'packaging-profiles.json'


def profiles(registry=DEFAULT_REGISTRY):
    path=Path(registry)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def write_profiles(items, registry):
    path=Path(registry);path.parent.mkdir(parents=True,exist_ok=True)
    # ponytail: one local UI process writes this file; use SQLite transactions for multiple server processes.
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def checked_model(model, dataset):
    import torch
    path=Path(model).resolve()
    config=torch.load(path,map_location='cpu',weights_only=True)['config']
    threshold=config.get('threshold')
    if threshold is None or not math.isfinite(float(threshold)):
        raise ValueError('模型尚未校准阈值，请先完成建库和验证集校准')
    if Path(config['dataset']).resolve()!=Path(dataset).resolve():
        raise ValueError('模型与该包装的数据集不对应，不能绑定到此参考库')
    return str(path)


def register(name, manufacturer, description, dataset, model='', registry=DEFAULT_REGISTRY):
    name=name.strip()
    if not name: raise ValueError('请填写包装名称/规格')
    if len(name)>120 or len(manufacturer)>200 or len(description)>2000:
        raise ValueError('包装信息过长')
    validate(dataset)
    items=profiles(registry)
    if any(item['name']==name for item in items.values()):
        raise ValueError('包装名称已存在；新版本请使用不同名称')
    ident=uuid.uuid4().hex
    items[ident]={'name':name,'manufacturer':manufacturer.strip(),'description':description.strip(),
                  'dataset':str(Path(dataset).resolve()),'model':checked_model(model,dataset) if model.strip() else ''}
    write_profiles(items,registry)
    return ident


def attach_model(ident, dataset, model, registry=DEFAULT_REGISTRY):
    items=profiles(registry);item=items[ident]
    if Path(dataset).resolve()!=Path(item['dataset']).resolve():
        raise ValueError('当前数据目录与所选包装不一致，请重新选择包装')
    item['model']=checked_model(model,dataset)
    write_profiles(items,registry)


def reference(ident, registry=DEFAULT_REGISTRY):
    item=profiles(registry)[ident]
    if not item['model']: raise ValueError('此包装尚未建库并校准，不能检测')
    checked_model(item['model'],item['dataset'])
    return item
