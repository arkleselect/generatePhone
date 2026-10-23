"""Run the trial whole-image defect classifier on an image or folder."""

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data/models/date-defect-cls-curated-50e-20260929.pt"
LABELS = {
    "normal": "正常",
    "blur": "模糊",
    "missing_chars": "缺码",
    "partial_break": "断码",
    "stain": "污渍",
}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def main():
    parser = argparse.ArgumentParser(description="测试日期缺陷整图分类模型")
    parser.add_argument("path", type=Path, help="单张图片或图片文件夹")
    parser.add_argument("--model", type=Path, default=MODEL, help="模型文件路径")
    args = parser.parse_args()

    if not args.model.is_file():
        parser.error(f"模型不存在：{args.model}")
    if args.path.is_file():
        images = [args.path]
    elif args.path.is_dir():
        images = sorted(p for p in args.path.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)
    else:
        parser.error(f"图片或文件夹不存在：{args.path}")
    if not images:
        parser.error("没有找到支持的图片")

    model = YOLO(str(args.model))
    for image, result in zip(images, model.predict(source=[str(p) for p in images], imgsz=224, batch=8, verbose=False)):
        class_id = result.probs.top1
        label = result.names[class_id]
        print(f"{image}\t{LABELS.get(label, label)} ({label})\t{result.probs.top1conf.item():.1%}")


if __name__ == "__main__":
    main()
