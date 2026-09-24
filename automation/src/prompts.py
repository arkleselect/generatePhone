import json
import re
from pathlib import Path
from typing import List


def load_prompts(path: str) -> List[str]:
    """Load prompts from a JSON file.

    Accepts either:
      - {"prompt1": "...", "prompt2": "..."}   (dict — values used in key order)
      - ["...", "..."]                          (list of strings)
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"prompts file not found: {path}")
    # utf-8-sig transparently handles a leading BOM if present
    data = json.loads(p.read_text(encoding="utf-8-sig"))

    if isinstance(data, dict):
        prompts = [str(v) for v in data.values()]
    elif isinstance(data, list):
        prompts = [str(v) for v in data]
    else:
        raise ValueError(
            f"prompts file must be a dict or list, got {type(data).__name__}"
        )

    prompts = [s.strip() for s in prompts if s and str(s).strip()]
    if not prompts:
        raise ValueError(f"no prompts found in {path}")
    return prompts


def slugify(text: str, max_len: int = 60) -> str:
    """Mirror the extension's slugifyPrompt — lowercase, kebab, trim."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = s[:max_len]
    s = s.rstrip("-")
    return s or "image"


# Industrial templates share the catalog consumed by the Java service and Vue UI.
CATALOG_PATH = Path(__file__).resolve().parents[2] / 'config/defects.json'
DEFECTS = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


def defect_key(value: str) -> str:
    """Accept stable Java identifiers, dataset names and Chinese display labels."""
    for key, definition in DEFECTS.items():
        if value in (key, definition['datasetType'], definition['label']):
            return key
    raise ValueError('未知缺陷类型：' + value)


def build_defect_prompt(defect_type: str, date_text: str | None = None, suffix: str = '') -> str:
    """Generate one concrete, auditable sample while preserving the reference composition."""
    import random
    key = defect_key(defect_type)
    definition = DEFECTS[key]
    if key == 'custom' and not suffix.strip():
        raise ValueError('自定义缺陷需要 custom_prompt_suffix')
    if len(suffix) > 4000:
        raise ValueError('补充提示词最多4000字符')
    positions = '喷码中的局部数字'
    if date_text:
        from datetime import datetime
        try:
            datetime.strptime(date_text.replace('.', '').replace('-', ''), '%Y%m%d')
        except ValueError as exc:
            raise ValueError('date_text 应为有效的 yyyyMMdd、yyyy.MM.dd 或 yyyy-MM-dd 日期') from exc
        if not re.fullmatch(r'\d{8}|\d{4}([.-])\d{2}\1\d{2}', date_text):
            raise ValueError('日期格式无效')
        digits = [index+1 for index, char in enumerate(date_text) if char.isdigit()]
        count = 2 if key == 'multi_break' else 1
        selected = sorted(random.sample(digits, count))
        positions = '、'.join(f'第{i}位「{date_text[i-1]}」' for i in selected)
    effect = definition['effect'].format(positions=positions, part='局部笔画', direction='右', object='少量浅灰色碎屑', description=suffix)
    date_instruction = ('先在原喷码区域建立完整日期 ' + date_text + '，再施加指定缺陷。位置按阅读顺序编号，与产品旋转无关。') if date_text else '沿用参考图日期内容，只修改指定缺陷；不要随意新增或更换日期。'
    return '\n'.join([
        '请使用上传的原图实际生成一张工业视觉训练样本，不要仅返回文字，不要生成拼图。',
        '产品为红色塑料肠衣包装的火腿肠，白色背景、真实简洁的工厂采集照片风格。以参考图为准，保持主体、背景、光照、角度、颜色、材质、摆放姿势和整体构图一致；原背景不是白色时也不要擅自替换。',
        '仅修改生产日期喷码区域以及实现指定缺陷必需的紧邻区域，其余区域尽量不变。不继承旧缺陷。喷码保留自然细小点阵和肠衣纹理，避免电脑描边文字。',
        date_instruction, '本次唯一主要效果：' + effect + ('。程度：中度。' if definition['severity'] else '。'),
        '字符缺失后其余字符保持原位，不前移、不重新居中、不压缩间距。正常样本的日期应完整清晰。',
        '不做海报风，不添加额外文字、水印、标注框、箭头、无关物体或夸张艺术效果。',
        ('额外要求：' + suffix) if suffix else '',
    ]).strip()
