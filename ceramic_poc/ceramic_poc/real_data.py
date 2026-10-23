"""Import an officially downloaded MVTec AD category without inventing real data."""
import random
import shutil
from pathlib import Path

from .data import write_manifest,validate


def import_mvtec(source,destination,category='tile',normal_train_limit=20):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if (source/category).is_dir(): source=source/category
    if destination.exists(): raise ValueError('Destination exists')
    normal=sorted((source/'train/good').glob('*.png'))
    if len(normal)<5 or not (source/'test').is_dir(): raise ValueError('Expected official category/train/good and category/test directories')
    if normal_train_limit<1: raise ValueError('Normal training limit must be positive')
    rng=random.Random(20261008);rng.shuffle(normal)
    count=max(1,round(len(normal)*.2))
    rows=[]
    def add(path,split,label,defect):
        ident=f'{path.parent.parent.name}_{path.parent.name}_{path.stem}'
        row=dict(id=ident,file=f'{split}/{label}/{ident}.png',label=label,defect_type=defect,prompt='',base_id=ident,seed='',split=split,batch='MVTecAD_original',source_type='REAL')
        target=destination/row['file'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);rows.append(row)
    for i,path in enumerate(normal[:count+normal_train_limit]): add(path,'val' if i<count else 'train','good','good')
    for folder in sorted((source/'test').iterdir()):
        if not folder.is_dir(): continue
        paths=sorted(folder.glob('*.png'));rng.shuffle(paths)
        if folder.name=='good':
            for path in paths: add(path,'test','good','good')
        else:
            # Original defect test images split once into calibration and final test; record IDs to freeze this split.
            for i,path in enumerate(paths): add(path,'val' if i<len(paths)//2 else 'test','bad',folder.name)
    write_manifest(destination,rows)
    return validate(destination)
