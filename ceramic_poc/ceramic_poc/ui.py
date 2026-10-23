"""Local-only Gradio UI for data import, feature-bank training and inspection."""
import json
from pathlib import Path

import gradio as gr
from PIL import Image

from .data import image_path, import_dataset, records, validate
from .profiles import profiles, register, attach_model, reference


def build_app(default_dataset, default_model=""):
    def choices():
        return [('临时实验（手动填写数据和模型）','')]+[(item['name'],ident) for ident,item in profiles().items()]

    def select_profile(ident):
        item=profiles().get(ident)
        if not item:
            return str(Path(default_dataset).resolve()),default_model,'','','',None,None,None,False
        return item['dataset'],item['model'],item['name'],item['manufacturer'],item['description'],None,None,None,False

    def save_profile(name,manufacturer,description,root,model):
        ident=register(name,manufacturer,description,root,model)
        return gr.Dropdown(choices=choices(),value=ident),f'已登记：{name}。'+('模型与阈值已绑定。' if model.strip() else '请到训练页建立参考库。')

    def overview(root):
        report=validate(root)
        thumbnails=[(str(image_path(root,r)),f'{r["id"]} · {r["split"]} · {r["defect_type"]}') for r in records(root)]
        return report,thumbnails

    def fit(root,output,size,ratio,backbone,device,tile_size,profile):
        import subprocess
        import sys
        if profile and Path(root).resolve()!=Path(profiles()[profile]['dataset']).resolve():
            raise gr.Error('数据目录与所选包装不一致，请重新选择包装')
        logs=[]
        commands=[
            [sys.executable,'-u','-m','ceramic_poc.cli','train',root,output,'--size',str(int(size)),
             '--ratio',str(ratio),'--backbone',backbone,'--device',device,'--tile-size',str(int(tile_size))],
            [sys.executable,'-u','-m','ceramic_poc.cli','calibrate',str(Path(output)/'model.pt'),root,'--device',device],
        ]
        yield 'Training started; extracting normal features…',''
        for command in commands:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            try:
                for line in process.stdout:
                    logs.append(line.rstrip())
                    yield '\n'.join(logs[-200:]),''
                if process.wait()!=0:
                    yield '\n'.join(logs[-200:])+'\nTraining/calibration failed',''
                    return
            finally:
                if process.poll() is None: process.terminate();process.wait()
        model=str(Path(output)/'calibrated.pt')
        if profile:
            attach_model(profile,root,model)
            logs.append('已绑定到所选包装参考库；后续检测使用此模型及其校准阈值。')
        yield '\n'.join(logs[-200:]),model

    def infer(image,weights,device,use_manual,override,profile):
        from .model import Detector
        from .evaluate import visualization
        if image is None: raise gr.Error('Upload an image')
        item=reference(profile) if profile else None
        if item: weights=item['model']
        detector=Detector.load(weights,device)
        threshold=float(override) if use_manual else detector.config.get('threshold')
        import math
        if threshold is None or not math.isfinite(threshold): raise gr.Error('Calibrate a finite threshold or enter a manual threshold')
        prediction=detector.predict(image)
        heat,overlay=visualization(image,prediction,detector.config)
        return heat,overlay,{'score':prediction['score'],'threshold':threshold,'decision':'NG' if prediction['score']>=threshold else 'OK',
                            'latency_ms':prediction['latency_ms'],'packaging':item['name'] if item else '临时实验',
                            'manufacturer':item['manufacturer'] if item else '',
                            'model':str(Path(weights).resolve()),'manual_threshold':bool(use_manual),
                            'note':'Heatmap is for visual inspection; no pixel-level accuracy claim'}

    def batch(weights,root,output,device,profile):
        from .evaluate import evaluate
        if profile:
            item=reference(profile);weights=item['model'];root=item['dataset']
        return evaluate(weights,root,output,device)

    with gr.Blocks(title='小样本异常检测 · 包装参考库') as demo:
        gr.Markdown('# 小样本异常检测 · 包装参考库\n每种包装使用自己的正常参考库和校准阈值。当前瓷砖数据为流程验证；火腿肠包装需导入对应真实数据。')
        profile=gr.Dropdown(choices=choices(),value='',label='选择包装参考库')
        dataset=gr.Textbox(value=str(Path(default_dataset).resolve()),label='数据集目录')
        with gr.Tab('包装参考库'):
            name=gr.Textbox(label='包装名称/规格（例如：红色细包装 30g）')
            manufacturer=gr.Textbox(label='适用厂家（外观相近且验证通过的厂家可共用）')
            description=gr.Textbox(label='长度、直径、颜色、印刷和拍摄条件',lines=3)
            gr.Markdown('先在数据集页导入对应图片，再登记包装。可绑定已有校准模型；模型路径留空则先登记数据，训练完成后自动绑定。新包装请勿直接绑定其他包装模型。')
            save=gr.Button('登记新包装参考库')
            status=gr.Textbox(label='参考库状态',interactive=False)
        with gr.Tab('数据集'):
            refresh=gr.Button('校验并查看数据集')
            summary=gr.JSON(label='数量、类别、划分与近重复检查')
            gallery=gr.Gallery(label='图片',columns=5)
            refresh.click(overview,[dataset],[summary,gallery])
            source=gr.Textbox(label='已有图片目录（包含 metadata.csv）')
            destination=gr.Textbox(label='导入目标目录（必须不存在）')
            gr.Button('导入并校验').click(import_dataset,[source,destination],[summary])
            gr.Markdown('将 PNG 图片及 metadata.csv 放在一个目录后导入。metadata.csv 中明确填写来源和集合，系统不会随机拆分同源图片。生图提示词与断点记录由命令行导出。')
        with gr.Tab('训练'):
            run=gr.Textbox(value='runs/ceramic_phase1',label='新训练输出目录')
            size=gr.Number(value=256,label='输入尺寸（原图保持 1024；细缺陷需对照更高尺寸）',precision=0)
            ratio=gr.Number(value=.01,label='特征库采样比例')
            backbone=gr.Dropdown(['resnet18','wide_resnet50_2'],value='resnet18',label='ImageNet 预训练骨干')
            device=gr.Dropdown(['auto','cpu','cuda'],value='auto',label='设备')
            tile=gr.Number(value=0,label='原图分块尺寸；0 为整图，512 可做高分辨率对照',precision=0)
            start=gr.Button('建立特征库并用验证集校准')
            logs=gr.Textbox(label='训练日志',lines=14)
            weights=gr.Textbox(value=default_model,label='模型路径（可填写已有 calibrated.pt）')
            start.click(fit,[dataset,run,size,ratio,backbone,device,tile,profile],[logs,weights])
        with gr.Tab('检测与评估'):
            image=gr.Image(type='pil',sources=['upload'],format='png',label='原始图片')
            use_manual=gr.Checkbox(value=False,label='使用手动阈值')
            override=gr.Number(value=0,label='手动阈值（勾选后生效）')
            detect=gr.Button('检测')
            with gr.Row():
                heat=gr.Image(label='异常热力图',format='png',buttons=['download','fullscreen']);overlay=gr.Image(label='叠加结果',format='png',buttons=['download','fullscreen'])
            prediction=gr.JSON(label='评分、OK/NG、推理时间')
            detect.click(infer,[image,weights,device,use_manual,override,profile],[heat,overlay,prediction])
            evaluation=gr.Textbox(value='runs/ceramic_phase1_test',label='新测试报告目录')
            gr.Button('使用冻结阈值评估测试集').click(batch,[weights,dataset,evaluation,device,profile],[prediction])
        save.click(save_profile,[name,manufacturer,description,dataset,weights],[profile,status])
        profile.change(select_profile,[profile],[dataset,weights,name,manufacturer,description,heat,overlay,prediction,use_manual])
    return demo
