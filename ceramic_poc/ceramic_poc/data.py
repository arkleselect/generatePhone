"""Manifest import and leakage checks; no automatic random image split."""
import csv
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

FIELDS = ['id', 'file', 'label', 'defect_type', 'prompt', 'base_id', 'seed', 'split', 'batch', 'source_type']


def records(root):
    root = Path(root).resolve()
    with (root / 'metadata.csv').open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not set(FIELDS) <= set(reader.fieldnames or []):
            raise ValueError(f'metadata.csv requires {FIELDS}')
        return list(reader)


def image_path(root, row):
    root = Path(root).resolve()
    path = (root / row['file']).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != '.png':
        raise ValueError(f'Unsafe/non-PNG path: {row["file"]}')
    return path


def validate(root, expected_size=1024):
    rows = records(root)
    if not rows:
        raise ValueError('Empty dataset')
    ids, files, roots, hashes, near = set(), set(), {}, {}, []
    for row in rows:
        if not row['id'] or row['id'] in ids or row['file'] in files:
            raise ValueError('Empty/duplicate image ID or filename')
        ids.add(row['id']); files.add(row['file'])
        if row['label'] not in {'good', 'bad'} or row['split'] not in {'train', 'val', 'test'}:
            raise ValueError('Invalid label or split')
        if row['split'] == 'train' and row['label'] != 'good':
            raise ValueError('Defect image must never enter the training bank')
        if (row['label'] == 'good') != (row['defect_type'] == 'good'):
            raise ValueError('Label and defect type disagree')
        if not row['base_id']:
            raise ValueError('base_id is required for source grouping')
        previous = roots.setdefault(row['base_id'], row['split'])
        if previous != row['split']:
            raise ValueError(f'Source leakage: {row["base_id"]}')
        path = image_path(root, row)
        expected = f'{row["split"]}/{row["label"]}/'
        if not row['file'].startswith(expected):
            raise ValueError(f'Image must be inside {expected}')
        with Image.open(path) as image:
            if image.format != 'PNG' or (expected_size and row['source_type']=='AI' and image.size != (expected_size, expected_size)):
                raise ValueError(f'Invalid image format/size: {path}')
            pixels = np.array(image.convert('RGB'))
            digest = hashlib.sha256(pixels.tobytes()).hexdigest()
            # ponytail: O(n²) low-resolution similarity is adequate for 260 images; use indexed perceptual features at larger scale.
            tiny = np.array(image.convert('L').resize((32,32)), dtype=float)
        if digest in hashes:
            raise ValueError(f'Duplicate decoded pixels: {row["id"]} and {hashes[digest]}')
        hashes[digest] = row['id']
        near.append((row['id'], row['split'], tiny))
    pairs = [(a[0], b[0]) for i,a in enumerate(near) for b in near[i+1:]
             if a[1] != b[1] and np.mean(np.abs(a[2]-b[2])) < 2]
    return {'count':len(rows), 'splits':dict(Counter(f'{r["split"]}/{r["label"]}' for r in rows)),
            'types':dict(Counter(r['defect_type'] for r in rows)),
            'cross_split_near_duplicates':pairs,
            'near_duplicate_note':'32x32 grayscale mean absolute difference < 2; manual review required, not proof of duplication'}


def import_dataset(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    report = validate(source)
    if destination.exists():
        raise ValueError('Destination already exists; choose a new directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        stage = Path(temporary)/'dataset'; stage.mkdir()
        shutil.copy2(source/'metadata.csv', stage/'metadata.csv')
        for row in records(source):
            target = stage / row['file']; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_path(source,row), target)
        (stage/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        validate(stage)
        stage.rename(destination)
    return report


def write_manifest(root, rows):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root/'metadata.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
