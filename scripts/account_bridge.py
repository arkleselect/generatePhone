#!/usr/bin/env python3
"""Move confirmed local jobs to/from the current account's image tool, without an AI API."""
import argparse
import json
import mimetypes
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid


def request(base, path, body=None, content_type="application/json"):
    """Use the loopback application API only; never handle ChatGPT login credentials."""
    req = urllib.request.Request(base + path, data=body, headers={
        "Content-Type": content_type, "X-HamLab-Request": "1",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read()).get("message", "Local request failed")
        except (ValueError, UnicodeDecodeError):
            message = f"Local request failed ({error.code})"
        raise SystemExit(message) from None
    except urllib.error.URLError:
        raise SystemExit("Cannot connect to the local HamLab backend; start the application first.") from None


def upload(args):
    """Upload the original generated file exactly once, preserving its received bytes."""
    source = Path(args.file).resolve()
    if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
        raise SystemExit("Image file missing or exceeds 20 MB.")
    boundary = "HamLab" + uuid.uuid4().hex
    body = bytearray()
    for name, value in {"actualModel": args.model, "channel": args.channel}.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="result{source.suffix}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    body.extend(source.read_bytes())
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    return request(args.base, f"/api/tasks/{args.task}/result", bytes(body), f"multipart/form-data; boundary={boundary}")


def main():
    """Expose explicit inspect/complete/fail actions; inspecting never initiates image generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8080", choices=["http://127.0.0.1:8080", "http://127.0.0.1:5173"])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("next")
    complete = commands.add_parser("complete")
    complete.add_argument("task")
    complete.add_argument("file")
    complete.add_argument("--model", default="", help="Actual model only if confirmed; blank means unknown")
    complete.add_argument("--channel", choices=["CODEX_IMAGE_TOOL", "MANUAL_CHATGPT"], default="CODEX_IMAGE_TOOL")
    fail = commands.add_parser("fail")
    fail.add_argument("task")
    fail.add_argument("reason")
    fail.add_argument("--uncertain", action="store_true")
    args = parser.parse_args()
    if args.command == "next":
        result = request(args.base, "/api/account/next")
    elif args.command == "complete":
        result = upload(args)
    else:
        result = request(args.base, f"/api/tasks/{args.task}/failure", json.dumps({"reason": args.reason, "uncertain": args.uncertain}).encode())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
