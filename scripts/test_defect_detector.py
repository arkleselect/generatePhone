"""Run the cropped YOLO trial on full images and draw boxes in full-image coordinates."""
from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

parser = argparse.ArgumentParser()
parser.add_argument('model', type=Path)
parser.add_argument('images', type=Path, nargs='+')
parser.add_argument('--crop', default='0.33,0.43,0.65,0.59', help='normalized left,top,right,bottom used for training')
parser.add_argument('--conf', type=float, default=0.25)
args = parser.parse_args()
left, top, right, bottom = map(float, args.crop.split(','))
assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
assert 0 < args.conf <= 1
model = YOLO(args.model)
output = Path(__file__).resolve().parents[1] / 'output/detection_tests'
output.mkdir(parents=True, exist_ok=True)
try:
    font = ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc', 24)
except OSError:
    font = ImageFont.load_default()
names = {'blur': '模糊', 'missing_chars': '日期不全', 'partial_break': '断码', 'stain': '脏污'}
for path in dict.fromkeys(args.images):
    with Image.open(path) as source:
        image = source.convert('RGB')
    width, height = image.size
    x0, y0, x1, y1 = round(left * width), round(top * height), round(right * width), round(bottom * height)
    result = model.predict(image.crop((x0, y0, x1, y1)), imgsz=960, conf=0.001, iou=0.3, max_det=5, verbose=False)[0]
    draw = ImageDraw.Draw(image)
    print(path)
    detected = [box for box in result.boxes if float(box.conf[0]) >= args.conf]
    if not detected:
        print(f'  未检出置信度达到 {args.conf:.0%} 的缺陷；这不等于确认图片正常。')
        if len(result.boxes):
            candidate = max(result.boxes, key=lambda box: float(box.conf[0]))
            label = names.get(result.names[int(candidate.cls[0])], result.names[int(candidate.cls[0])])
            print(f'  最高候选：{label} {float(candidate.conf[0]):.1%}（低于阈值，不画框）')
    for box in detected:
        x_min, y_min, x_max, y_max = (float(v) for v in box.xyxy[0])
        rectangle = (x_min + x0, y_min + y0, x_max + x0, y_max + y0)
        label = names.get(result.names[int(box.cls[0])], result.names[int(box.cls[0])])
        text = f'{label} {float(box.conf[0]):.1%}'
        draw.rectangle(rectangle, outline='#1677ff', width=4)
        draw.text((rectangle[0], max(0, rectangle[1] - 30)), text, fill='#1677ff', font=font, stroke_width=1)
        print(f'  {text}  {[round(v) for v in rectangle]}')
    destination = output / f'{path.stem}_detected.png'
    image.save(destination)
    print(f'  saved {destination}')
