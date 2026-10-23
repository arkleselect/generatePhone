import argparse
import json


def main():
    parser=argparse.ArgumentParser(description='Ceramic normal-only PatchCore PoC')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan');p.add_argument('directory');p.add_argument('--phase',type=int,choices=[1,2],default=1);p.add_argument('--difficulty',choices=['standard','subtle'],default='subtle')
    p=sub.add_parser('generate');p.add_argument('directory');p.add_argument('--limit',type=int);p.add_argument('--model',default='gpt-image-2.5')
    p=sub.add_parser('validate');p.add_argument('dataset')
    p=sub.add_parser('import');p.add_argument('source');p.add_argument('destination')
    p=sub.add_parser('train');p.add_argument('dataset');p.add_argument('output');p.add_argument('--size',type=int,default=256);p.add_argument('--ratio',type=float,default=.01);p.add_argument('--tile-size',type=int,default=0);p.add_argument('--backbone',choices=['resnet18','wide_resnet50_2'],default='resnet18');p.add_argument('--device',default='auto')
    p=sub.add_parser('calibrate');p.add_argument('model');p.add_argument('dataset');p.add_argument('--device',default='auto')
    p=sub.add_parser('evaluate');p.add_argument('model');p.add_argument('dataset');p.add_argument('output');p.add_argument('--device',default='auto')
    p=sub.add_parser('predict');p.add_argument('model');p.add_argument('image');p.add_argument('output');p.add_argument('--device',default='auto');p.add_argument('--threshold',type=float)
    p=sub.add_parser('ui');p.add_argument('--dataset',default='../datasets/ceramic_tile_phase1');p.add_argument('--port',type=int,default=7860);p.add_argument('--model',default='')
    p=sub.add_parser('mvtec-import');p.add_argument('source');p.add_argument('destination');p.add_argument('--category',default='tile');p.add_argument('--normal-train-limit',type=int,default=20)
    args=parser.parse_args()
    if args.command=='plan':
        from .generation import plan
        print(plan(args.directory,args.phase,args.difficulty))
    elif args.command=='generate':
        from .generation import generate
        print(generate(args.directory,args.limit,args.model))
    elif args.command=='validate':
        from .data import validate
        print(json.dumps(validate(args.dataset),indent=2))
    elif args.command=='import':
        from .data import import_dataset
        print(import_dataset(args.source,args.destination))
    elif args.command=='train':
        from .model import train
        print(train(args.dataset,args.output,args.size,args.ratio,args.backbone,args.device,args.tile_size))
    elif args.command=='calibrate':
        from .model import calibrate
        print(calibrate(args.model,args.dataset,args.device))
    elif args.command=='evaluate':
        from .evaluate import evaluate
        print(json.dumps(evaluate(args.model,args.dataset,args.output,args.device),indent=2))
    elif args.command=='predict':
        from pathlib import Path
        from PIL import Image
        import numpy as np
        from .model import Detector
        from .evaluate import visualization
        detector=Detector.load(args.model,args.device)
        threshold=args.threshold if args.threshold is not None else detector.config.get('threshold')
        if threshold is None: raise ValueError('Calibrate first or supply --threshold')
        output=Path(args.output)
        if output.exists(): raise ValueError('Output directory exists')
        image=Image.open(args.image).convert('RGB');result=detector.predict(image)
        heat,overlay=visualization(image,result,detector.config);output.mkdir(parents=True)
        heat.save(output/'heatmap.png');overlay.save(output/'overlay.png');np.save(output/'raw_anomaly_map.npy',result['map'])
        report={k:v for k,v in result.items() if k!='map'};report.update(threshold=threshold,decision='NG' if result['score']>=threshold else 'OK')
        (output/'prediction.json').write_text(json.dumps(report,indent=2));print(report)
    elif args.command=='mvtec-import':
        from .real_data import import_mvtec
        print(import_mvtec(args.source,args.destination,args.category,args.normal_train_limit))
    else:
        import os
        for name in ('NO_PROXY','no_proxy'):
            os.environ[name]=','.join(filter(None,[os.environ.get(name,''),'127.0.0.1','localhost']))
        from .ui import build_app
        build_app(args.dataset,args.model).queue(default_concurrency_limit=1).launch(server_name='127.0.0.1',server_port=args.port,inbrowser=False)


if __name__ == "__main__":
    main()
