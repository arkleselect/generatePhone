"""Anomalib's PatchCore implementation, raw scores, and validation-only calibration."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision.transforms import v2
from anomalib.models.image.patchcore.torch_model import PatchcoreModel

from .data import image_path, records, validate


def device_for(name='auto'):
    if name == 'auto':
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if name == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA unavailable; install CUDA PyTorch on the RTX 3080 computer')
    return torch.device(name)


def tiles(image, tile_size):
    if not tile_size:
        yield (0,0,image.width,image.height),image
        return
    if tile_size > min(image.size) or tile_size < 32:
        raise ValueError('Tile size must be between 32 and the smallest image dimension')
    stride=max(1,tile_size//2)
    positions=lambda extent: sorted(set([*range(0,extent-tile_size+1,stride),extent-tile_size]))
    for y in positions(image.height):
        for x in positions(image.width):
            box=(x,y,x+tile_size,y+tile_size)
            yield box,image.crop(box)


def tensor(image, size):
    transform=v2.Compose([v2.Resize((size,size)),v2.ToImage(),v2.ToDtype(torch.float32,scale=True),
                          v2.Normalize(mean=[.485,.456,.406],std=[.229,.224,.225])])
    return transform(image.convert('RGB')).unsqueeze(0)


class Detector:
    def __init__(self, config, state=None, device='auto'):
        self.config=config
        self.device=device_for(device)
        torch.set_num_threads(min(4,torch.get_num_threads()))
        self.model=PatchcoreModel(layers=['layer2','layer3'],backbone=config['backbone'],pre_trained=state is None,num_neighbors=3).to(self.device)
        if state is not None:
            self.model.load_state_dict(state)
        self.model.eval()

    @classmethod
    def load(cls, path, device='auto'):
        # Only load checkpoints created by this project; weights_only excludes arbitrary Python objects.
        saved=torch.load(path,map_location='cpu',weights_only=True)
        return cls(saved['config'],saved['state_dict'],device)

    def sync(self):
        if self.device.type=='cuda': torch.cuda.synchronize(self.device)

    @torch.inference_mode()
    def predict(self, image):
        if not isinstance(image,Image.Image):
            with Image.open(image) as opened: image=opened.convert('RGB')
        else: image=image.convert('RGB')
        self.sync(); started=time.perf_counter()
        anomaly=np.zeros((image.height,image.width),dtype=np.float32)
        weights=np.zeros_like(anomaly); scores=[]
        for (left,top,right,bottom),piece in tiles(image,self.config['tile_size']):
            output=self.model(tensor(piece,self.config['input_size']).to(self.device))
            heat=output.anomaly_map[0,0].detach().float().cpu().numpy()
            heat=np.asarray(Image.fromarray(heat).resize(piece.size,Image.Resampling.BILINEAR))
            anomaly[top:bottom,left:right]+=heat; weights[top:bottom,left:right]+=1
            scores.append(float(output.pred_score[0].detach().cpu()))
        self.sync()
        return {'score':max(scores),'map':anomaly/weights,'latency_ms':(time.perf_counter()-started)*1000}


def train(dataset, output, input_size=256, ratio=.01, backbone='resnet18', device='auto', tile_size=0, log=print):
    report=validate(dataset)
    if not 32<=input_size<=1024 or not 0<ratio<=1:
        raise ValueError('Input size 32..1024 and coreset ratio (0,1] required')
    output=Path(output)
    if output.exists(): raise ValueError('Output directory exists; choose a new run')
    rows=records(dataset)
    good=[r for r in rows if r['split']=='train' and r['label']=='good']
    if not good: raise ValueError('No normal training samples')
    config={'input_size':int(input_size),'tile_size':int(tile_size),'ratio':float(ratio),'backbone':backbone,
            'training_sources':[r['base_id'] for r in good], 'dataset':str(Path(dataset).resolve()),
            'training_pixel_hashes':[],'threshold':None}
    torch.manual_seed(20261008)
    config["feature_sampling_seed"]=20261008
    detector=Detector(config,device=device)
    detector.model.train()
    with torch.inference_mode():
        for i,row in enumerate(good):
            log(f'Extract normal features {i+1}/{len(good)}: {row["id"]}')
            with Image.open(image_path(dataset,row)) as image:
                image=image.convert('RGB')
                config['training_pixel_hashes'].append(hashlib.sha256(np.array(image).tobytes()).hexdigest())
                for _,piece in tiles(image,tile_size):
                    detector.model(tensor(piece,input_size).to(detector.device))
        feature_count=sum(len(e) for e in detector.model.embedding_store)
        count=int(feature_count*ratio)
        if count<3: raise ValueError('Coreset has fewer than 3 features; increase sampling ratio/input size')
        log(f'Sample normal feature bank: {feature_count} -> {count}; no backpropagation/epochs')
        detector.model.subsample_embedding(sampling_ratio=ratio)
    detector.model.eval()
    config['normalization_note']='Raw PatchCore scores; thresholds are calibrated on validation images only'
    output.mkdir(parents=True)
    weights=output/'model.pt'
    torch.save({'config':config,'state_dict':{k:v.detach().cpu() for k,v in detector.model.state_dict().items()}},weights)
    (output/'dataset-validation.json').write_text(json.dumps(report,indent=2))
    (output/'config.json').write_text(json.dumps(config,indent=2))
    log(f'Saved {weights}')
    return weights


def score_split(detector, dataset, split):
    rows=[r for r in records(dataset) if r['split']==split]
    if not rows: raise ValueError(f'No {split} images')
    result=[]
    first=image_path(dataset,rows[0]); detector.predict(first)  # warm-up excluded from latency statistics
    for row in rows:
        if row['base_id'] in detector.config['training_sources']:
            raise ValueError('Training source in evaluation split')
        path=image_path(dataset,row)
        with Image.open(path) as image:
            digest=hashlib.sha256(np.array(image.convert('RGB')).tobytes()).hexdigest()
        if digest in detector.config['training_pixel_hashes']:
            raise ValueError('Training pixels in evaluation split')
        prediction=detector.predict(path)
        result.append({'id':row['id'],'label':int(row['label']=='bad'),'defect_type':row['defect_type'],
                       'score':prediction['score'],'latency_ms':prediction['latency_ms'],'batch':row['batch']})
    return result


def calibrate(model_path,dataset,device='auto'):
    from sklearn.metrics import f1_score
    validate(dataset)
    detector=Detector.load(model_path,device)
    rows=score_split(detector,dataset,'val')
    labels=np.array([r['label'] for r in rows]); scores=np.array([r['score'] for r in rows])
    if set(labels)!={0,1}: raise ValueError('Validation requires both normal and defect images')
    thresholds=np.r_[np.unique(scores),np.nextafter(scores.max(),np.inf)]
    # Tie-break toward fewer normal false positives, then higher recall.
    def quality(t):
        predictions=scores>=t
        return (f1_score(labels,predictions),-int(np.sum(predictions & (labels==0))),int(np.sum(predictions & (labels==1))))
    threshold=float(max(thresholds,key=quality))
    saved=torch.load(model_path,map_location='cpu',weights_only=True)
    saved['config']['threshold']=threshold
    saved['config']['validation_scores']=rows
    heat_ranges=[]
    for row in records(dataset):
        if row['split']=='val':
            heat=detector.predict(image_path(dataset,row))['map']
            heat_ranges.extend([float(np.percentile(heat,1)),float(np.percentile(heat,99))])
    saved['config']['heat_range']=[min(heat_ranges),max(heat_ranges)]
    target=Path(model_path).with_name('calibrated.pt')
    if target.exists(): raise ValueError('Calibrated checkpoint already exists; choose a new run')
    torch.save(saved,target)
    target.with_suffix('.json').write_text(json.dumps(saved['config'],indent=2))
    return target
