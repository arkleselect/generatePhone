"""Prepare the manually boxed defect export for a small YOLO detection trial."""
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from random import Random
from zipfile import ZipFile
import sys
from PIL import Image

archive = Path(sys.argv[1])
normal = Path(sys.argv[2])
out = Path(sys.argv[3])
crop = tuple(map(float, sys.argv[4].split(','))) if len(sys.argv) > 4 else None
assert crop is None or len(crop) == 4 and 0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1
normal_images = sorted(normal.glob('*.png')) if normal.is_dir() else [normal]
assert archive.is_file() and normal_images and all(path.is_file() for path in normal_images)
assert len({path.stem for path in normal_images}) == len(normal_images)
assert not out.exists(), f"Refusing to overwrite {out}"
def prepare_image(data: bytes):
    if crop is None:
        return data, None
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        left, top, right, bottom = (round(crop[0] * width), round(crop[1] * height), round(crop[2] * width), round(crop[3] * height))
        output = BytesIO()
        image.crop((left, top, right, bottom)).save(output, format='PNG')
    return output.getvalue(), (left / width, top / height, (right - left) / width, (bottom - top) / height)
with ZipFile(archive) as z:
    names = set(z.namelist())
    classes = z.read('classes.txt').decode().splitlines()
    assert classes and len(classes) == len(set(classes))
    images = sorted(n for n in names if n.startswith('images/') and not n.endswith('/'))
    groups = defaultdict(list)
    for image in images:
        stem = Path(image).stem
        label = f'labels/{stem}.txt'
        assert label in names, f'Missing {label}'
        lines = z.read(label).decode().splitlines()
        assert lines, f'No defect boxes: {label}'
        categories = set()
        for line in lines:
            values = line.split()
            assert len(values) == 5, (label, line)
            category = int(values[0])
            x, y, w, h = map(float, values[1:])
            assert 0 <= category < len(classes) and w > 0 and h > 0
            assert 0 <= x - w / 2 and x + w / 2 <= 1
            assert 0 <= y - h / 2 and y + h / 2 <= 1
            categories.add(category)
        groups[tuple(sorted(categories))].append((image, label))
    assert {category for combination in groups for category in combination} == set(range(len(classes)))
    rng = Random(20260929)
    split = {}
    # ponytail: Grouping by exact class combination is only for tiny trials; split by source with multilabel stratification once diverse sources exist.
    for categories, group in groups.items():
        rng.shuffle(group)
        count = max(1, round(len(group) * 0.2)) if len(group) > 1 else 0
        for image, label in group[:count]:
            split[image] = ('val', label, categories)
        for image, label in group[count:]:
            split[image] = ('train', label, categories)
    for image, (part, label, _) in split.items():
        for kind in ('images', 'labels'):
            (out / kind / part).mkdir(parents=True, exist_ok=True)
        data, region = prepare_image(z.read(image))
        (out / 'images' / part / Path(image).name).write_bytes(data)
        if region is None:
            (out / 'labels' / part / Path(label).name).write_bytes(z.read(label))
        else:
            left, top, width, height = region
            transformed = []
            for line in z.read(label).decode().splitlines():
                category, x, y, w, h = line.split()
                x, y, w, h = (float(x) - left) / width, (float(y) - top) / height, float(w) / width, float(h) / height
                assert x - w / 2 >= 0 and x + w / 2 <= 1 and y - h / 2 >= 0 and y + h / 2 <= 1, label
                transformed.append(f'{category} {x} {y} {w} {h}')
            (out / 'labels' / part / Path(label).name).write_text('\n'.join(transformed) + '\n')
normal_val_count = max(1, round(len(normal_images) * 0.2)) if len(normal_images) > 1 else 0
rng.shuffle(normal_images)
for index, path in enumerate(normal_images):
    part = 'val' if index < normal_val_count else 'train'
    for kind in ('images', 'labels'):
        (out / kind / part).mkdir(parents=True, exist_ok=True)
    (out / 'originals' / 'normal').mkdir(parents=True, exist_ok=True)
    (out / 'originals' / 'normal' / path.name).write_bytes(path.read_bytes())
    (out / 'images' / part / path.name).write_bytes(prepare_image(path.read_bytes())[0])
    (out / 'labels' / part / f'{path.stem}.txt').write_text('')
(out / 'data.yaml').write_text('path: ' + str(out.resolve()) + '\ntrain: images/train\nval: images/val\nnames:\n' + ''.join(f'  {i}: {name}\n' for i, name in enumerate(classes)))
if crop is not None:
    (out / 'crop.txt').write_text(','.join(map(str, crop)) + '\n')
(out / 'split.csv').write_text('image,split,classes\n' + ''.join(f'{Path(image).name},{part},{"|".join(classes[category] for category in categories)}\n' for image, (part,_,categories) in sorted(split.items())) + ''.join(f'{path.name},{"val" if index < normal_val_count else "train"},normal-empty-label\n' for index, path in enumerate(normal_images)))
print(f'Prepared {len(images)} defects and {len(normal_images)} normals: {sum(v[0] == "train" for v in split.values()) + len(normal_images) - normal_val_count} train, {sum(v[0] == "val" for v in split.values()) + normal_val_count} val; {classes}')
