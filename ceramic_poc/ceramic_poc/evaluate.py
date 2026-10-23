"""Frozen-threshold image-level evaluation; no claimed pixel accuracy."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

from .data import validate, records
from .model import Detector, score_split


def metrics(rows,threshold):
    labels=np.array([r['label'] for r in rows]);scores=np.array([r['score'] for r in rows])
    prediction=scores>=threshold
    tn,fp,fn,tp=confusion_matrix(labels,prediction,labels=[0,1]).ravel()
    latency=[r['latency_ms'] for r in rows]
    return {'count':len(rows),'AUROC':float(roc_auc_score(labels,scores)) if len(set(labels))==2 else None,
            'precision':float(precision_score(labels,prediction,zero_division=0)),
            'recall':float(recall_score(labels,prediction,zero_division=0)),
            'F1':float(f1_score(labels,prediction,zero_division=0)),
            'false_positive_rate':float(fp/(tn+fp)) if tn+fp else None,
            'false_negative_rate':float(fn/(tp+fn)) if tp+fn else None,
            'confusion_matrix':[[int(tn),int(fp)],[int(fn),int(tp)]],
            'mean_ms':float(np.mean(latency)),'P50_ms':float(np.percentile(latency,50)),
            'P95_ms':float(np.percentile(latency,95))}


def evaluate(model_path,dataset,output,device='auto'):
    validation=validate(dataset)
    detector=Detector.load(model_path,device)
    threshold=detector.config.get('threshold')
    if threshold is None: raise ValueError('Calibrate on validation data first')
    rows=score_split(detector,dataset,'test')
    root=Path(output)
    if root.exists(): raise ValueError('Evaluation directory already exists; choose a new path')
    root.mkdir(parents=True)
    report=metrics(rows,threshold)
    report.update(threshold=threshold,device=str(detector.device),input_size=detector.config['input_size'],tile_size=detector.config['tile_size'],
                  synthetic_only=all(r['source_type']=='AI' for r in records(dataset)),
                  conclusion='Small-sample pipeline verification only; no real-production or pixel-level accuracy conclusion',
                  dataset_validation=validation)
    normal=[r for r in rows if r['label']==0]
    report['by_defect']={name:metrics(normal+[r for r in rows if r['defect_type']==name],threshold)
                         for name in sorted({r['defect_type'] for r in rows if r['label']==1})}
    report['by_generation_batch']={batch:metrics([r for r in rows if r['batch']==batch],threshold) for batch in sorted({r['batch'] for r in rows})}
    (root/'metrics.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    with (root/'predictions.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    cm=np.array(report['confusion_matrix']);axes[0].imshow(cm,cmap='Blues')
    for (y,x),value in np.ndenumerate(cm):axes[0].text(x,y,str(value),ha='center',va='center')
    axes[0].set(xticks=[0,1],yticks=[0,1],xticklabels=['OK','NG'],yticklabels=['OK','NG'],xlabel='Predicted',ylabel='Actual',title='Image-level confusion matrix')
    for label,name in [(0,'Normal'),(1,'Defect')]:
        axes[1].hist([r['score'] for r in rows if r['label']==label],bins=10,alpha=.5,label=name)
    axes[1].axvline(threshold,color='black',linestyle='--');axes[1].legend();axes[1].set(title='Raw anomaly scores',xlabel='Score')
    fig.tight_layout();fig.savefig(root/'evaluation.png');plt.close(fig)
    return report


def visualization(image,prediction,config):
    from PIL import Image
    raw=prediction['map']
    low,high=config.get('heat_range',[float(raw.min()),float(raw.max())])
    normalized=np.clip((raw-low)/max(high-low,1e-12),0,1)
    colored=(plt.get_cmap('turbo')(normalized)[...,:3]*255).astype(np.uint8)
    heat=Image.fromarray(colored)
    return heat,Image.blend(image.convert('RGB'),heat,.45)
