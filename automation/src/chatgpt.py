"""ChatGPT image-gen automation, ported from the extension's content.js."""

import asyncio
import datetime as _dt
import json
import os
import time
import uuid
from pathlib import Path

import re
from urllib.parse import urlparse, urljoin
from PIL import Image
from io import BytesIO
from page_selectors import composer, send_button, GENERATED, LOADING

from prompts import slugify


class RateLimited(Exception):
    pass


class GenerationFailed(Exception):
    pass


class GenerationTimeout(GenerationFailed):
    """A submitted request may still finish; retry waiting, never silently resubmit it."""


class ContentDenied(Exception):
    pass


def log(msg: str, level: str = "info"):
    prefix = {"info": "[info]", "success": "[ ok ]", "error": "[err ]"}.get(
        level, "[info]"
    )
    print(f"{prefix} {msg}", flush=True)


async def _generated_sources(page):
    """Localized selectors share the same image validation and de-duplicate matched nodes."""
    return await page.locator(','.join(GENERATED)).evaluate_all(
        "nodes => [...new Set(nodes.filter(i => i.complete && i.naturalWidth > 0).map(i => i.currentSrc || i.src))]")


async def _count_generated(page) -> int:
    return len(await _generated_sources(page))


async def _last_image_src(page):
    sources = await _generated_sources(page)
    return sources[-1] if sources else None


async def _last_assistant_text(page) -> str:
    """Full innerText of the most recent conversation turn (assistant reply).

    Used to capture refusal / denial text when we don't get an image, so we
    can build a corpus of denial phrasings across runs.
    """
    try:
        return await page.evaluate(
            """() => {
                const turns = document.querySelectorAll('[data-message-author-role="assistant"]');
                if (turns.length === 0) return '';
                const last = turns[turns.length - 1];
                return (last.innerText || '').trim();
            }"""
        )
    except Exception:
        return ""


def log_no_image_response(
    output_dir: Path,
    prompt: str,
    error_type: str,
    error_msg: str,
    response_text: str,
) -> None:
    """Append a row to no_image_log.jsonl capturing what ChatGPT said instead
    of generating an image. Builds a corpus of refusal/denial variations
    that future detection rules can target.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "error_type": error_type,
        "error_msg": error_msg,
        "prompt": prompt,
        "response_text": response_text,
    }
    log_path = output_dir / "no_image_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def _check_for_errors(page):
    """Check only the latest assistant reply; never mistake the user's prompt for an error."""
    text = (await _last_assistant_text(page)).lower()
    if any(value in text for value in ['hit the team plan limit', 'hit the limit for image generation', 'image generation limit', '达到图片生成上限', '已达到图像生成限制']):
        raise RateLimited('账号图片额度已用尽，请在网页确认后再继续')
    if any(value in text for value in ['experienced an error when generating', 'error generating images', '生成图片时出错', '生成图像时出错']):
        raise GenerationFailed('网页明确报告图片生成失败')
    if any(value in text for value in ['violate our guardrails', 'content policy', '违反内容政策', '无法满足此图片生成请求']):
        raise ContentDenied('网页拒绝生成此内容')


async def start_new_chat(page):
    """Keep upstream navigation; each industrial sample invokes this independently."""
    await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
    await composer(page)


async def upload_reference(page, source: Path):
    """Use file inputs first, then the visible localized upload menu as a fallback."""
    if not source.is_file():
        raise ValueError('参考图不存在')
    inputs = page.locator('input[type="file"]')
    if await inputs.count():
        await inputs.first.set_input_files(str(source))
    else:
        await page.get_by_role('button', name=re.compile(r'^(添加文件等|Add files and more)$', re.I)).click()
        async with page.expect_file_chooser(timeout=15000) as chooser:
            await page.get_by_text(re.compile(r'^(添加照片和文件|Add photos & files|Add photos and files)$', re.I)).click()
        await (await chooser.value).set_files(str(source))
    # Uploads can be asynchronous. Require a visible attachment and no upload progress.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        errors = page.get_by_text(re.compile(r'上传失败|无法上传|Upload failed|Unable to upload', re.I))
        if await errors.first.is_visible():
            raise GenerationFailed('参考图上传失败')
        attached = await page.get_by_text(source.name, exact=False).first.is_visible()
        thumbnails = page.locator('form img, [data-testid="composer"] img, [data-testid*="attachment"] img')
        if (attached or await thumbnails.count()) and not await page.get_by_role('progressbar').count():
            await asyncio.sleep(1)
            return
        await asyncio.sleep(0.5)
    raise TimeoutError('参考图上传未确认完成')


async def type_prompt(page, text: str):
    """Fill through Playwright so literal HTML in user text is never interpreted."""
    await (await composer(page)).fill(text)


async def submit_prompt(page):
    await (await send_button(page, timeout=120)).click()


async def wait_for_image_generation(page, prev_count: int, timeout_s: int = 360):
    """One deadline covers loading, localization, full image loading and double-render selection."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        await _check_for_errors(page)
        if await _count_generated(page) > prev_count and not await page.locator(LOADING).count():
            log("image generated", "success")
            return
        multigen = page.locator('[data-testid="image-paragen-multigen"]')
        if await multigen.count():
            choice = multigen.get_by_role('button', name=re.compile(r'Image 1|图片 1|图像 1', re.I)).first
            if await choice.is_visible():
                await choice.click()
        await asyncio.sleep(1)
    raise GenerationTimeout('等待图片超时；可能仍在生成，请保留会话核实')


def trusted_image_url(src):
    """Do not forward account state or follow redirects to unrelated download hosts."""
    parsed = urlparse(src)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and any(host == domain or host.endswith('.' + domain)
        for domain in ('chatgpt.com', 'oaiusercontent.com', 'oaistatic.com', 'openai.com'))


async def download_image(page, prompt: str, output_dir: Path) -> Path:
    """Reuse the upstream rendered-image URL, with scoped session cookies and validated bytes."""
    src = await _last_image_src(page)
    if not src:
        raise GenerationFailed('页面中尚无完整生成图片')
    if src.startswith('blob:https://chatgpt.com/'):
        encoded = await page.evaluate("""async src => {
            const response = await fetch(src, {signal: AbortSignal.timeout(60000)});
            const blob = await response.blob();
            if (blob.size > 52428800) throw new Error('Image too large');
            return await new Promise((resolve,reject) => {const r = new FileReader();
                r.onload = () => resolve(r.result.split(',')[1]); r.onerror = reject; r.readAsDataURL(blob);});
        }""", src)
        import base64
        data = base64.b64decode(encoded)
    else:
        for _ in range(5):
            if not trusted_image_url(src):
                raise GenerationFailed('生成图片下载域名未识别，请检查页面，不会发送账号凭据')
            response = await page.context.request.get(src, timeout=60000, max_redirects=0)
            if response.status in (301,302,303,307,308):
                src = urljoin(src, response.headers.get('location', ''))
                await response.dispose()
                continue
            try:
                if not response.ok:
                    raise GenerationFailed('生成图片下载失败，HTTP ' + str(response.status))
                if int(response.headers.get('content-length', '0')) > 50*1024*1024:
                    raise GenerationFailed('下载图片超过50MB')
                data = await response.body()
            finally:
                await response.dispose()
            break
        else:
            raise GenerationFailed('图片下载重定向次数过多')
    if len(data) > 50*1024*1024:
        raise GenerationFailed('下载图片超过50MB')
    with Image.open(BytesIO(data)) as image:
        if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height > 24_000_000:
            raise GenerationFailed('下载内容不是受支持的图片或像素过大')
        ext = {'PNG': '.png','JPEG': '.jpg','WEBP': '.webp'}[image.format]
        image.verify()
    output_dir.mkdir(parents=True, exist_ok=True)
    fpath = output_dir / f"{slugify(prompt)}-{uuid.uuid4()}{ext}"
    temporary = fpath.with_suffix(fpath.suffix + '.part')
    temporary.write_bytes(data); temporary.replace(fpath)
    log(f"downloaded -> {fpath.name}", "success")
    return fpath


async def generate_one(page, prompt: str, output_dir: Path) -> Path:
    prev = await _count_generated(page)
    await type_prompt(page, prompt)
    await submit_prompt(page)
    await wait_for_image_generation(page, prev)
    return await download_image(page, prompt, output_dir)


async def _record_no_image(page, output_dir: Path, prompt: str, exc: Exception):
    """Capture the assistant's text reply when generation produced no image."""
    text = await _last_assistant_text(page)
    log_no_image_response(
        output_dir, prompt, type(exc).__name__, str(exc), text
    )


async def generate_batch(page, prompts, output_dir: Path):
    """Generate images for every prompt. Yields (index, prompt, result_path_or_error)."""
    await start_new_chat(page)
    results = []
    for i, prompt in enumerate(prompts):
        log(f"[{i + 1}/{len(prompts)}] {prompt[:70]}")
        try:
            path = await generate_one(page, prompt, output_dir)
            results.append({"prompt": prompt, "ok": True, "path": str(path)})
        except RateLimited as e:
            await _record_no_image(page, output_dir, prompt, e)
            log(f"rate limited — stopping: {e}", "error")
            results.append({"prompt": prompt, "ok": False, "error": "rate_limited"})
            break
        except ContentDenied as e:
            await _record_no_image(page, output_dir, prompt, e)
            log(f"content denied: {e}", "error")
            results.append({"prompt": prompt, "ok": False, "error": "content_denied"})
            await asyncio.sleep(5)
        except GenerationFailed as e:
            await _record_no_image(page, output_dir, prompt, e)
            log(f"generation failed: {e}", "error")
            results.append({"prompt": prompt, "ok": False, "error": str(e)})
            await asyncio.sleep(30)
        except Exception as e:
            try:
                await _record_no_image(page, output_dir, prompt, e)
            except Exception:
                pass
            log(f"unexpected error: {e}", "error")
            results.append({"prompt": prompt, "ok": False, "error": str(e)})
            await asyncio.sleep(10)
    return results
